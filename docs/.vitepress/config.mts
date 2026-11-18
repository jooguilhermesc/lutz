import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'Lutz',
  description: 'Extração validada para revisões sistemáticas — documentação oficial',
  base: '/lutz/',

  head: [
    ['link', { rel: 'icon', href: '/lutz/logo.png' }],
  ],

  themeConfig: {
    logo: '/logo.png',
    siteTitle: 'Lutz',

    nav: [
      { text: 'Guia', link: '/guide/getting-started' },
      { text: 'Especificação', link: '/spec-1.0' },
      { text: 'GitHub', link: 'https://github.com/jooguilhermesc/lutz' },
    ],

    sidebar: [
      {
        text: 'Uso',
        items: [
          { text: 'Começar', link: '/guide/getting-started' },
          { text: 'Configuração', link: '/configuracao' },
          { text: 'Referência da CLI', link: '/referencia-cli' },
          { text: 'Do 0.5 para o 1.0', link: '/upgrade-0.5-para-1.0' },
        ],
      },
      {
        text: 'Referência',
        items: [
          { text: 'Especificação 1.0', link: '/spec-1.0' },
          { text: 'Métodos estatísticos', link: '/metodos-estatisticos' },
          { text: 'Validação com artigo real', link: '/validacao-e2e' },
        ],
      },
    ],

    socialLinks: [
      { icon: 'github', link: 'https://github.com/jooguilhermesc/lutz' },
    ],

    footer: {
      message: 'Lançado sob a licença MIT.',
      copyright: 'Copyright © 2026 João Guilherme Silva Cabral & Anna Karoline Azevedo Farias',
    },

    search: {
      provider: 'local',
    },
  },
})
