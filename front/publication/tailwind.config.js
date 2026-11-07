// Même configuration que le bloc `tailwind.config` de front/prototype/index.html (à garder
// identiques). Utilisée par `make css` pour construire la feuille de style de la version web.
module.exports = {
  content: { relative: true, files: ['../prototype/index.html'] },
  theme: {
    extend: {
      fontFamily: {
        serif: ['"Source Serif 4"', 'Georgia', 'serif'],
        sans: ['system-ui', '-apple-system', '"Segoe UI"', 'sans-serif'],
      },
      colors: {
        page: 'var(--page)', surface: 'var(--surface)', ink: 'var(--ink)',
        ink2: 'var(--ink-2)', muted: 'var(--muted)', rule: 'var(--rule)',
        accent: 'var(--series-1)', accentsoft: 'var(--accent-soft)',
      },
    },
  },
};
