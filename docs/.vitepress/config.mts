import { defineConfig } from 'vitepress'

export default defineConfig({
  title: 'Lutz',
  description: 'Triagem de artigos acadêmicos com IA — documentação oficial',
  base: '/lutz/',

  head: [
    ['link', { rel: 'icon', href: '/lutz/logo.png' }],
  ],

  themeConfig: {
    logo: '/logo.png',
    siteTitle: 'Lutz',

    nav: [
      { text: 'Guia', link: '/guide/getting-started' },
      { text: 'Interface Web', link: '/guide/interface/home' },
      { text: 'GitHub', link: 'https://github.com/jooguilhermesc/lutz' },
    ],

    sidebar: [
      {
        text: 'Início',
        items: [
          { text: 'Introdução', link: '/guide/getting-started' },
          { text: 'Configuração do Ambiente', link: '/guide/configuration' },
        ],
      },
      {
        text: 'Análise Semântica',
        items: [
          { text: 'Visão geral', link: '/guide/analytics' },
        ],
      },
      {
        text: 'Interface Web',
        items: [
          { text: 'Visão geral', link: '/guide/interface/home' },
          { text: 'Aba Biblioteca', link: '/guide/interface/biblioteca' },
          { text: 'Aba Resultados', link: '/guide/interface/resultados' },
          { text: 'Aba Relatórios', link: '/guide/interface/relatorios' },
          { text: 'Histórico', link: '/guide/interface/historico' },
          { text: 'Configurações', link: '/guide/interface/configuracoes' },
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
