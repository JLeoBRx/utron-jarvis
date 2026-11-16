"""Contas, senhas, sessões, bloqueio por tentativas e recuperação de acesso.

Decisões (docs/security/PORTAL_AUTHENTICATION.md):
* a senha é guardada com scrypt e conferida em tempo constante; a mensagem de falha é sempre a mesma, exista ou
  não a conta, esteja ela bloqueada ou não;
* o banco guarda só o resumo do token de sessão e do token de recuperação;
* sessão com prazo absoluto e prazo de inatividade; trocar ou recuperar a senha encerra as outras sessões;
* não existe conta padrão: o primeiro administrador é criado por comando no servidor.
"""
from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as Db

from safra_foundation import passwords, tokens
from safra_foundation.errors import Conflict, InvalidInput, NotAuthenticated, NotFound, RateLimited

from ..cms import audit
from ..config import Settings
from ..domain import permissions
from ..domain.models import RecoveryToken, RolePermission, Session, User, as_utc, utcnow
from ..infrastructure.ratelimit import RateLimiter

_EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,189}\.[^@\s]{2,}$")
_FAST_PARAMS = passwords.ScryptParams(n=2 ** 10, r=8, p=1)       # só no ambiente de teste
INVALID = "E-mail ou senha incorretos."
LAST_SEEN_STEP = timedelta(seconds=60)


@dataclass(frozen=True)
class Identity:
    """Quem está fazendo o pedido: usuário, papel e permissões lidos do banco a cada pedido."""
    user_id: int
    email: str
    name: str
    role: str
    permissions: frozenset[str]
    session_id: int
    csrf_token: str

    def can(self, permission: str) -> bool:
        return permission in self.permissions


class AuthService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.params = _FAST_PARAMS if settings.environment == "test" else passwords.DEFAULT_PARAMS
        self.login_limiter = RateLimiter(settings.login_attempts_per_ip, 300)
        self.recovery_limiter = RateLimiter(5, 900)
        self._hashing = threading.BoundedSemaphore(2)              # cada cálculo usa muita memória: no máximo 2 juntos
        self._dummy_hash = passwords.hash_password("senha-que-ninguem-usa-0000", self.params)

    # ------------------------------------------------------------------ senhas
    def _hash(self, password: str) -> str:
        with self._hashing:
            return passwords.hash_password(password, self.params)

    def _verify(self, password: str, encoded: str) -> bool:
        with self._hashing:
            return passwords.verify_password(password, encoded)

    # ------------------------------------------------------------------ contas
    @staticmethod
    def normalize_email(email: str) -> str:
        email = (email or "").strip().lower()
        if not _EMAIL.match(email) or len(email) > 254:
            raise InvalidInput("Informe um e-mail válido.", details={"field": "email"})
        return email

    def count_users(self, db: Db) -> int:
        return db.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None))) or 0

    def create_user(self, db: Db, *, email: str, name: str, role: str, password: str | None = None,
                    actor_id: int | None = None, ip: str = "") -> User:
        """Cria a conta. Sem ``password`` ela nasce sem senha: o dono define a sua por um token de recuperação."""
        email = self.normalize_email(email)
        name = (name or "").strip()
        if not 1 <= len(name) <= 120:
            raise InvalidInput("Informe o nome (até 120 caracteres).", details={"field": "name"})
        if role not in permissions.ROLES:
            raise InvalidInput("Papel inexistente.", details={"field": "role"})
        if db.scalar(select(User.id).where(User.email == email)):
            raise Conflict("Já existe uma conta com este e-mail.")
        user = User(email=email, name=name, role_key=role,
                    password_hash=self._hash(password) if password else "",
                    password_changed_at=utcnow() if password else None)
        db.add(user)
        db.flush()
        audit.record(db, "user.create", actor_id=actor_id, target_type="user", target_id=user.id,
                     detail={"role": role}, ip=ip)
        return user

    def _active_admins(self, db: Db, *, excluding: int | None = None) -> int:
        query = select(func.count()).select_from(User).where(
            User.role_key == permissions.ADMINISTRADOR, User.is_active.is_(True), User.deleted_at.is_(None))
        if excluding is not None:
            query = query.where(User.id != excluding)
        return db.scalar(query) or 0

    def update_user(self, db: Db, user_id: int, *, name: str | None = None, role: str | None = None,
                    is_active: bool | None = None, actor_id: int | None = None, ip: str = "") -> User:
        user = self.get_user(db, user_id)
        losing_admin = user.role_key == permissions.ADMINISTRADOR and user.is_active and (
            (role is not None and role != permissions.ADMINISTRADOR) or is_active is False)
        if losing_admin and self._active_admins(db, excluding=user.id) == 0:
            raise Conflict("Esta é a única conta de administrador ativa: ela não pode ser rebaixada nem desativada.")
        changes: dict = {}
        if name is not None:
            name = name.strip()
            if not 1 <= len(name) <= 120:
                raise InvalidInput("Informe o nome (até 120 caracteres).", details={"field": "name"})
            user.name, changes["name"] = name, True
        if role is not None:
            if role not in permissions.ROLES:
                raise InvalidInput("Papel inexistente.", details={"field": "role"})
            if role != user.role_key:
                changes["role"] = {"from": user.role_key, "to": role}
                user.role_key = role
        if is_active is not None and is_active != user.is_active:
            user.is_active, changes["is_active"] = is_active, is_active
            if not is_active:
                self.revoke_sessions(db, user.id)
        user.updated_at = utcnow()
        audit.record(db, "user.update", actor_id=actor_id, target_type="user", target_id=user.id, detail=changes, ip=ip)
        return user

    def get_user(self, db: Db, user_id: int) -> User:
        user = db.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise NotFound("Usuário não encontrado.")
        return user

    def list_users(self, db: Db) -> list[User]:
        return list(db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.name)))

    # ------------------------------------------------------------------ entrada e sessões
    def login(self, db: Db, *, email: str, password: str, ip: str, user_agent: str) -> tuple[str, Session]:
        """Devolve ``(token, sessão)``. Qualquer falha tem a mesma resposta e o mesmo custo de tempo."""
        if not self.login_limiter.hit(ip or "desconhecido"):
            audit.record(db, "login.rate_limited", ip=ip)
            db.commit()
            raise RateLimited("Muitas tentativas de entrada. Aguarde alguns minutos.")
        email = (email or "").strip().lower()
        user = db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
        now = utcnow()
        usable = user is not None and user.is_active and bool(user.password_hash)
        locked = usable and user.locked_until is not None and as_utc(user.locked_until) > now
        ok = self._verify(password or "", user.password_hash if usable else self._dummy_hash) and usable and not locked
        if not ok:
            if usable and not locked:
                user.failed_attempts += 1
                if user.failed_attempts >= self.settings.lockout_threshold:
                    extra = user.failed_attempts - self.settings.lockout_threshold
                    minutes = min(self.settings.lockout_minutes * (2 ** extra), 24 * 60)
                    user.locked_until = now + timedelta(minutes=minutes)
                    audit.record(db, "login.locked", target_type="user", target_id=user.id,
                                 detail={"minutes": minutes}, ip=ip)
            audit.record(db, "login.failed", target_type="user", target_id=user.id if user else "", ip=ip)
            db.commit()                                             # o contador de falhas precisa persistir
            raise NotAuthenticated(INVALID)
        user.failed_attempts, user.locked_until, user.last_login_at = 0, None, now
        if passwords.needs_rehash(user.password_hash, self.params):
            user.password_hash = self._hash(password)
        token = tokens.new_token(32)
        session = Session(user_id=user.id, token_digest=tokens.token_digest(token), csrf_token=tokens.new_token(24),
                          expires_at=now + timedelta(hours=self.settings.session_absolute_hours),
                          last_seen_at=now, ip=(ip or "")[:64], user_agent=(user_agent or "")[:256])
        db.add(session)
        db.flush()
        audit.record(db, "login.ok", actor_id=user.id, target_type="session", target_id=session.id, ip=ip)
        return token, session

    def identify(self, db: Db, token: str | None) -> Identity | None:
        """Sessão válida → identidade com as permissões do papel ATUAL do usuário; senão ``None``."""
        if not token or len(token) > 200:
            return None
        session = db.scalar(select(Session).where(Session.token_digest == tokens.token_digest(token)))
        if session is None or session.revoked_at is not None:
            return None
        now = utcnow()
        idle = timedelta(minutes=self.settings.session_idle_minutes)
        if as_utc(session.expires_at) <= now or now - as_utc(session.last_seen_at) > idle:
            session.revoked_at = now
            db.commit()
            return None
        user = session.user
        if user is None or not user.is_active or user.deleted_at is not None:
            return None
        if now - as_utc(session.last_seen_at) > LAST_SEEN_STEP:
            session.last_seen_at = now
            db.commit()
        granted = frozenset(db.scalars(select(RolePermission.permission_key)
                                       .where(RolePermission.role_key == user.role_key)))
        return Identity(user_id=user.id, email=user.email, name=user.name, role=user.role_key, permissions=granted,
                        session_id=session.id, csrf_token=session.csrf_token)

    def logout(self, db: Db, identity: Identity, ip: str = "") -> None:
        db.execute(update(Session).where(Session.id == identity.session_id).values(revoked_at=utcnow()))
        audit.record(db, "logout", actor_id=identity.user_id, target_type="session", target_id=identity.session_id, ip=ip)

    def revoke_sessions(self, db: Db, user_id: int, *, except_session: int | None = None) -> int:
        query = update(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
        if except_session is not None:
            query = query.where(Session.id != except_session)
        return db.execute(query.values(revoked_at=utcnow())).rowcount or 0

    def list_sessions(self, db: Db, user_id: int) -> list[Session]:
        return list(db.scalars(select(Session).where(Session.user_id == user_id, Session.revoked_at.is_(None))
                               .order_by(Session.last_seen_at.desc())))

    # ------------------------------------------------------------------ troca e recuperação de senha
    def change_password(self, db: Db, identity: Identity, *, current: str, new: str, ip: str = "") -> None:
        user = self.get_user(db, identity.user_id)
        if not self._verify(current or "", user.password_hash or self._dummy_hash) or not user.password_hash:
            raise NotAuthenticated("A senha atual não confere.")
        user.password_hash, user.password_changed_at = self._hash(new), utcnow()
        self.revoke_sessions(db, user.id, except_session=identity.session_id)
        audit.record(db, "password.change", actor_id=user.id, target_type="user", target_id=user.id, ip=ip)

    def create_recovery_token(self, db: Db, user_id: int, *, actor_id: int | None = None, ip: str = "") -> str:
        """Token de uso único para o dono da conta definir uma senha nova. Mostrado UMA vez a quem o gerou."""
        user = self.get_user(db, user_id)
        db.execute(update(RecoveryToken).where(RecoveryToken.user_id == user.id, RecoveryToken.used_at.is_(None))
                   .values(used_at=utcnow()))                      # um token novo invalida os anteriores
        token = tokens.new_token(32)
        db.add(RecoveryToken(user_id=user.id, token_digest=tokens.token_digest(token), created_by=actor_id,
                             expires_at=utcnow() + timedelta(minutes=self.settings.recovery_token_minutes)))
        audit.record(db, "recovery.create", actor_id=actor_id, target_type="user", target_id=user.id, ip=ip)
        return token

    def recover(self, db: Db, *, token: str, new_password: str, ip: str) -> None:
        if not self.recovery_limiter.hit(ip or "desconhecido"):
            raise RateLimited("Muitas tentativas. Aguarde alguns minutos.")
        passwords.check_policy(new_password)
        row = db.scalar(select(RecoveryToken).where(RecoveryToken.token_digest == tokens.token_digest(token or "")))
        now = utcnow()
        if row is None or row.used_at is not None or as_utc(row.expires_at) <= now:
            audit.record(db, "recovery.failed", ip=ip)
            db.commit()
            raise NotAuthenticated("O código de recuperação é inválido ou expirou.")
        user = db.get(User, row.user_id)
        if user is None or user.deleted_at is not None or not user.is_active:
            raise NotAuthenticated("O código de recuperação é inválido ou expirou.")
        row.used_at = now
        user.password_hash, user.password_changed_at = self._hash(new_password), now
        user.failed_attempts, user.locked_until = 0, None
        self.revoke_sessions(db, user.id)
        audit.record(db, "recovery.used", actor_id=user.id, target_type="user", target_id=user.id, ip=ip)

    def purge_expired(self, db: Db, *, now: datetime | None = None) -> int:
        """Remove sessões vencidas há mais de um dia e tokens de recuperação vencidos. Chamado na inicialização."""
        from sqlalchemy import delete
        limit = (now or utcnow()) - timedelta(days=1)
        removed = db.execute(delete(Session).where(Session.expires_at < limit)).rowcount or 0
        removed += db.execute(delete(RecoveryToken).where(RecoveryToken.expires_at < limit)).rowcount or 0
        return removed
