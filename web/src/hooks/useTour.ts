import { driver } from 'driver.js'
import 'driver.js/dist/driver.css'
import { useLanguage } from '../contexts/LanguageContext'

interface TourCallbacks {
  openSettings: (section: 'results' | 'roadmap') => void
  closeSettings: () => void
}

export function useTour({ openSettings, closeSettings }: TourCallbacks) {
  const { t, lang } = useLanguage()

  function startTour() {
    const progressText = lang === 'en'
      ? '{{current}} of {{total}}'
      : lang === 'es'
      ? '{{current}} de {{total}}'
      : '{{current}} de {{total}}'
    const nextBtn = lang === 'en' ? 'Next →' : lang === 'es' ? 'Siguiente →' : 'Próximo →'
    const prevBtn = lang === 'en' ? '← Back' : lang === 'es' ? '← Anterior' : '← Anterior'
    const doneBtn = lang === 'en' ? 'Finish' : lang === 'es' ? 'Finalizar' : 'Concluir'

    const driverObj = driver({
      showProgress: true,
      progressText,
      nextBtnText: nextBtn,
      prevBtnText: prevBtn,
      doneBtnText: doneBtn,
      animate: true,
      overlayOpacity: 0.55,
      stagePadding: 8,
      stageRadius: 10,
      popoverClass: 'lutz-tour-popover',
      steps: [
        {
          popover: {
            title: t('tour.s0.title'),
            description: t('tour.s0.desc'),
            align: 'center',
          },
        },
        {
          element: '#tour-pipeline',
          popover: {
            title: t('tour.s1.title'),
            description: t('tour.s1.desc'),
            side: 'right',
            align: 'start',
          },
        },
        {
          element: '#tour-tab-biblioteca',
          popover: {
            title: t('tour.s2.title'),
            description: t('tour.s2.desc'),
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '#tour-tab-resultados',
          popover: {
            title: t('tour.s3.title'),
            description: t('tour.s3.desc'),
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '#tour-tab-relatorios',
          popover: {
            title: t('tour.s4.title'),
            description: t('tour.s4.desc'),
            side: 'bottom',
            align: 'start',
          },
        },
        {
          element: '#tour-criteria',
          popover: {
            title: t('tour.s5.title'),
            description: t('tour.s5.desc'),
            side: 'right',
            align: 'start',
          },
        },
        {
          element: '#tour-templates',
          popover: {
            title: t('tour.s6.title'),
            description: t('tour.s6.desc'),
            side: 'right',
            align: 'start',
          },
        },
        {
          element: '#tour-run-btn',
          popover: {
            title: t('tour.s7.title'),
            description: t('tour.s7.desc'),
            side: 'top',
            align: 'center',
          },
        },
        {
          element: '#tour-settings',
          popover: {
            title: t('tour.s8.title'),
            description: t('tour.s8.desc'),
            side: 'bottom',
            align: 'end',
            onNextClick: () => {
              openSettings('results')
              setTimeout(() => driverObj.moveNext(), 380)
            },
          },
        },
        {
          element: '#tour-settings-modal',
          onHighlightStarted: () => {
            document.getElementById('tour-verdict-categories')?.scrollIntoView({ block: 'start' })
          },
          popover: {
            title: t('tour.s9.title'),
            description: t('tour.s9.desc'),
            side: 'left',
            align: 'center',
            onPrevClick: () => {
              closeSettings()
              setTimeout(() => driverObj.movePrevious(), 200)
            },
          },
        },
        {
          element: '#tour-settings-modal',
          onHighlightStarted: () => {
            document.getElementById('tour-analysis-criteria')?.scrollIntoView({ block: 'start' })
          },
          popover: {
            title: t('tour.s10.title'),
            description: t('tour.s10.desc'),
            side: 'left',
            align: 'center',
            onNextClick: () => {
              closeSettings()
              setTimeout(() => driverObj.moveNext(), 200)
            },
          },
        },
        {
          element: '#tour-cost',
          popover: {
            title: t('tour.s11.title'),
            description: t('tour.s11.desc'),
            side: 'bottom',
            align: 'end',
          },
        },
        {
          element: '#tour-history',
          popover: {
            title: t('tour.s12.title'),
            description: t('tour.s12.desc'),
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
