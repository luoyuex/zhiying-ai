const prefersReducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches

/* ---------- 头部状态 ---------- */

const header = document.querySelector<HTMLElement>('[data-header]')
const navLinks = Array.from(
  document.querySelectorAll<HTMLAnchorElement>('.primary-nav a[data-section]'),
)
const spySections = Array.from(document.querySelectorAll<HTMLElement>('main section[id]'))

let scrollTicking = false

function updateScrollState(): void {
  const scrollY = window.scrollY
  header?.classList.toggle('is-scrolled', scrollY > 8)

  const current = spySections
    .filter((section) => section.getBoundingClientRect().top <= window.innerHeight * 0.36)
    .pop()
  const currentId = current?.dataset.navSection ?? current?.id ?? ''

  navLinks.forEach((link) => {
    const active = link.dataset.section === currentId
    link.classList.toggle('is-active', active)
    if (active) {
      link.setAttribute('aria-current', 'location')
    } else {
      link.removeAttribute('aria-current')
    }
  })

  scrollTicking = false
}

function onScroll(): void {
  if (scrollTicking) return
  scrollTicking = true
  window.requestAnimationFrame(updateScrollState)
}

window.addEventListener('scroll', onScroll, { passive: true })
window.addEventListener('resize', onScroll)
updateScrollState()

/* ---------- 移动菜单 ---------- */

const menuToggle = document.querySelector<HTMLButtonElement>('[data-menu-toggle]')
const menu = document.querySelector<HTMLElement>('[data-menu]')
const menuLinks = Array.from(document.querySelectorAll<HTMLAnchorElement>('[data-menu-link]'))
const menuFocusables = menu
  ? Array.from(menu.querySelectorAll<HTMLElement>('a[href], button:not([disabled])'))
  : []

function setMenu(open: boolean, returnFocus = false): void {
  if (!menu || !menuToggle) return

  document.body.classList.toggle('menu-open', open)
  menu.classList.toggle('is-open', open)
  menu.setAttribute('aria-hidden', String(!open))
  menu.inert = !open
  menuToggle.setAttribute('aria-expanded', String(open))
  menuToggle.setAttribute('aria-label', open ? '关闭菜单' : '打开菜单')

  if (open) {
    window.setTimeout(() => menuFocusables[0]?.focus(), 180)
  } else if (returnFocus) {
    menuToggle.focus()
  }
}

menuToggle?.addEventListener('click', () => {
  setMenu(!menu?.classList.contains('is-open'))
})

menuLinks.forEach((link) => {
  link.addEventListener('click', () => setMenu(false))
})

window.addEventListener('keydown', (event) => {
  if (!menu?.classList.contains('is-open')) return

  if (event.key === 'Escape') {
    event.preventDefault()
    setMenu(false, true)
    return
  }

  if (event.key !== 'Tab' || menuFocusables.length === 0) return

  const first = menuFocusables[0]
  const last = menuFocusables[menuFocusables.length - 1]
  const active = document.activeElement

  if (event.shiftKey && (active === first || !menu.contains(active))) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && active === last) {
    event.preventDefault()
    first.focus()
  }
})

window.matchMedia('(min-width: 941px)').addEventListener('change', (event) => {
  if (event.matches) setMenu(false)
})

/* ---------- 入场 ---------- */

const revealItems = Array.from(document.querySelectorAll<HTMLElement>('[data-reveal]'))
const revealAll =
  prefersReducedMotion ||
  new URLSearchParams(window.location.search).has('no-anim') ||
  !('IntersectionObserver' in window)

if (revealAll) {
  revealItems.forEach((item) => item.classList.add('is-in'))
} else {
  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return
        entry.target.classList.add('is-in')
        revealObserver.unobserve(entry.target)
      })
    },
    { threshold: 0.1, rootMargin: '0px 0px -5% 0px' },
  )

  revealItems.forEach((item) => revealObserver.observe(item))

  /* 兜底：即使没有滚动，也保证内容最终可见（利于渲染型爬虫与深链访问） */
  window.setTimeout(() => {
    revealItems.forEach((item) => item.classList.add('is-in'))
  }, 8000)
}

/* ---------- 分析师标签页 ---------- */

const tabs = Array.from(document.querySelectorAll<HTMLButtonElement>('[data-tab]'))

function selectTab(index: number, focus = false): void {
  tabs.forEach((tab, i) => {
    const selected = i === index
    tab.classList.toggle('is-active', selected)
    tab.setAttribute('aria-selected', String(selected))
    tab.tabIndex = selected ? 0 : -1

    const panelId = tab.getAttribute('aria-controls')
    const panel = panelId ? document.getElementById(panelId) : null
    if (panel) {
      panel.hidden = !selected
      panel.classList.toggle('is-active', selected)
    }
  })

  if (focus) tabs[index]?.focus()
}

tabs.forEach((tab, index) => {
  tab.addEventListener('click', () => selectTab(index))

  tab.addEventListener('keydown', (event) => {
    const key = event.key
    let next = index

    if (key === 'ArrowRight' || key === 'ArrowDown') next = (index + 1) % tabs.length
    else if (key === 'ArrowLeft' || key === 'ArrowUp') next = (index - 1 + tabs.length) % tabs.length
    else if (key === 'Home') next = 0
    else if (key === 'End') next = tabs.length - 1
    else return

    event.preventDefault()
    selectTab(next, true)
  })
})
