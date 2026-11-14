export function mountMotion() {
  const reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
  if (reducedMotion.matches || !('IntersectionObserver' in window)) return;
  const targets = [...document.querySelectorAll('[data-reveal]')];
  if (!targets.length) return;
  const observer = new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      entry.target.classList.add('is-visible');
      observer.unobserve(entry.target);
    }
  }, { threshold: 0.12, rootMargin: '0px 0px -15px 0px' });
  document.documentElement.classList.add('motion-ready');
  for (const group of document.querySelectorAll('.workflow, .tools')) {
    [...group.children].forEach((item, index) => item.style.setProperty('--reveal-delay', `${index * 90}ms`));
  }
  targets.forEach(target => observer.observe(target));
  reducedMotion.addEventListener('change', event => {
    if (!event.matches) return;
    observer.disconnect();
    document.documentElement.classList.remove('motion-ready');
  });
}
