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
        text: 'Interface Web',
        items: [
          { text: 'Dashboard (Home)', link: '/guide/interface/home' },
          { text: 'Biblioteca (Vetorização)', link: '/guide/interface/vetorizacao' },
          { text: 'Vector Store', link: '/guide/interface/vector-store' },
          { text: 'Análise', link: '/guide/interface/analise' },
          { text: 'Relatórios', link: '/guide/interface/relatorios' },
          { text: 'Citações', link: '/guide/interface/citacoes' },
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
