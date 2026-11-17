import { fileURLToPath, URL } from 'node:url';
import tailwindcss from '@tailwindcss/vite';
import react from '@vitejs/plugin-react';
import { defineConfig } from 'vite';

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { '@': fileURLToPath(new URL('./src', import.meta.url)) },
  },
  server: { host: '127.0.0.1', port: 5173 },
  preview: { host: '127.0.0.1', port: 4173 },
  build: {
    sourcemap: true,
    chunkSizeWarningLimit: 600,
    rolldownOptions: {
      output: {
        // Bibliotecas em pacotes separados: mudam pouco e ficam em cache entre deploys.
        codeSplitting: {
          groups: [
            { name: 'react', test: /node_modules[\\/](react|react-dom|react-router|scheduler)[\\/]/ },
            { name: 'supabase', test: /node_modules[\\/]@supabase[\\/]/ },
            // Visualizadores pesados (PDF/DOCX) ficam FORA: só são baixados ao abrir um arquivo.
            { name: 'vendor', test: /node_modules[\\/](?!pdfjs-dist|docx-preview|jszip)/ },
          ],
        },
      },
    },
  },
});
