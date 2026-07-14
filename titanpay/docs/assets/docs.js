document.querySelectorAll('pre').forEach((block) => {
  const btn = document.createElement('button');
  btn.className = 'copy-btn';
  btn.textContent = 'Copy';
  btn.type = 'button';
  btn.addEventListener('click', () => {
    navigator.clipboard.writeText(block.innerText.replace(/\nCopy$/, ''));
    btn.textContent = 'Copied';
    setTimeout(() => { btn.textContent = 'Copy'; }, 1500);
  });
  block.appendChild(btn);
});

const links = document.querySelectorAll('.sidebar a');
const sections = [...links]
  .map((a) => document.querySelector(a.getAttribute('href')))
  .filter(Boolean);

const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry) => {
    if (!entry.isIntersecting) return;
    links.forEach((l) => {
      l.classList.toggle('active', l.getAttribute('href') === '#' + entry.target.id);
    });
  });
}, { rootMargin: '-30% 0px -60% 0px', threshold: 0 });

sections.forEach((s) => observer.observe(s));
