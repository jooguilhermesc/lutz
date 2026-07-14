import { driver } from 'driver.js'
import 'driver.js/dist/driver.css'

export function useTour() {
  function startTour() {
    const driverObj = driver({
      showProgress: true,
      progressText: '{{current}} de {{total}}',
      nextBtnText: 'Próximo →',
      prevBtnText: '← Anterior',
      doneBtnText: 'Concluir',
      animate: true,
      overlayOpacity: 0.55,
      stagePadding: 8,
      stageRadius: 10,
      popoverClass: 'lutz-tour-popover',
      steps: [
        {
          popover: {
            title: '👋 Bem-vindo ao Lutz!',
            description:
              'Este tour rápido apresenta os elementos principais da interface. ' +
              'Use as setas para navegar ou pressione <kbd>Esc</kbd> para sair.',
            align: 'center',
          },
        },
        {
          element: '#tour-pipeline',
          popover: {
            title: 'Pipeline de trabalho',
            description:
              'Acompanhe o progresso em três etapas: ' +
              '<b>Biblioteca</b> → <b>Vetorizado</b> → <b>Análise</b>. ' +
              'Clique no botão de cada etapa para executar a ação ou ver detalhes.',
            side: 'right',
            align: 'start',
          },
        },
        {
          element: '#tour-tab-biblioteca',
          popover: {
            title: 'Aba Biblioteca',
            description:
              'Lista todos os artigos PDF do projeto. Carregue novos arquivos, ' +
              'renomeie automaticamente com IA e inicie a vetorização.',
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '#tour-tab-resultados',
          popover: {
            title: 'Aba Resultados',
            description:
              'Exibe os veredictos da análise RAG para cada artigo: ' +
              '<b>Incluir</b>, <b>Excluir</b> ou <b>Incerto</b>. ' +
              'Expanda um artigo para ver a justificativa completa do modelo.',
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '#tour-tab-relatorios',
          popover: {
            title: 'Aba Relatórios',
            description:
              'Lista todos os relatórios gerados. ' +
              'Baixe em PDF ou remova relatórios antigos.',
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '#tour-criteria',
          popover: {
            title: 'Critério de triagem',
            description:
              'Descreva aqui os critérios de inclusão e exclusão da sua revisão. ' +
              'Este texto é enviado ao LLM — quanto mais específico, melhor a triagem.',
            side: 'right',
            align: 'start',
          },
        },
        {
          element: '#tour-templates',
          popover: {
            title: 'Templates de prompt',
            description:
              'Clique num template para carregá-lo no campo de triagem. ' +
              'Salve seus próprios critérios com o campo "Salvar como…" para reutilizá-los.',
            side: 'right',
            align: 'start',
          },
        },
        {
          element: '#tour-provider',
          popover: {
            title: 'Provedor e Modelo LLM',
            description:
              'Selecione o provedor (Anthropic, OpenAI, OpenRouter, Docker) e o modelo ' +
              'que o Lutz usará para analisar os artigos.',
            side: 'right',
            align: 'start',
          },
        },
        {
          element: '#tour-emb-model',
          popover: {
            title: 'Modelo de Embedding',
            description:
              'Modelo usado para vetorizar os PDFs. Deve ser do mesmo provedor selecionado acima. ' +
              'Alterar este modelo requer re-vetorizar os artigos.',
            side: 'right',
            align: 'start',
          },
        },
        {
          element: '#tour-run-btn',
          popover: {
            title: '▶ Iniciar análise',
            description:
              'Com artigos vetorizados e critério preenchido, este botão dispara a análise RAG. ' +
              'Os veredictos aparecem em tempo real na aba Resultados.',
            side: 'top',
            align: 'center',
          },
        },
        {
          element: '#tour-cost',
          popover: {
            title: 'Estimativa de custo',
            description:
              'Custo estimado da próxima análise em USD, calculado pelo número de chunks ' +
              'vetorizados e pelo preço por token do modelo selecionado.',
            side: 'bottom',
            align: 'end',
          },
        },
        {
          element: '#tour-history',
          popover: {
            title: 'Histórico de análises',
            description:
              'Abre um painel lateral com execuções anteriores — data, modelo, tokens e duração. ' +
              'Clique em "Ver todos" para ir direto aos relatórios.',
            side: 'bottom',
            align: 'end',
          },
        },
        {
          element: '#tour-settings',
          popover: {
            title: '⚙ Configurações',
            description:
              'Ajuste provedor, chaves de API e idioma da interface. ' +
              'As mudanças entram em vigor imediatamente, sem reiniciar o servidor.',
            side: 'bottom',
            align: 'end',
          },
        },
      ],
    })

    driverObj.drive()
  }

  return { startTour }
}
