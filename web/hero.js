// Match the display card to four points on the photographed lens plane.
// A projective transform preserves the lens's taper as the hero resizes.
export function projectiveMatrix(points, width, height) {
  const [[x0, y0], [x1, y1], [x2, y2], [x3, y3]] = points;
  const dx1 = x1 - x2, dx2 = x3 - x2;
  const dy1 = y1 - y2, dy2 = y3 - y2;
  const sx = x0 - x1 + x2 - x3, sy = y0 - y1 + y2 - y3;
  const determinant = dx1 * dy2 - dx2 * dy1;
  const g = (sx * dy2 - dx2 * sy) / determinant;
  const h = (dx1 * sy - sx * dy1) / determinant;
  return [
    (x1 - x0 + g * x1) / width, (y1 - y0 + g * y1) / width, 0, g / width,
    (x3 - x0 + h * x3) / height, (y3 - y0 + h * y3) / height, 0, h / height,
    0, 0, 1, 0,
    x0, y0, 0, 1,
  ];
}

export function mountHero() {
  const stage = document.querySelector('.product-stage');
  const image = stage?.querySelector('.hero-glasses');
  const card = stage?.querySelector('.recipe-preview');
  if (!stage || !image || !card) return;

  // Clockwise corners on the flat lens plane, not the curved frame outline.
  // Keep opposite edges nearly parallel instead of tapering the card to the rim.
  const lensCorners = [[565, 280], [725, 263], [733, 366], [576, 383]];
  function alignCard() {
    if (!image.naturalWidth || !card.offsetWidth || !card.offsetHeight) return;
    const scale = image.offsetWidth / image.naturalWidth;
    const corners = lensCorners.map(([x, y]) => [
      image.offsetLeft + x * scale,
      image.offsetTop + y * scale,
    ]);
    const matrix = projectiveMatrix(corners, card.offsetWidth, card.offsetHeight);
    card.style.left = '0';
    card.style.top = '0';
    card.style.transformOrigin = '0 0';
    card.style.transform = `matrix3d(${matrix.join(',')})`;
  }
  const observer = new ResizeObserver(alignCard);
  observer.observe(stage);
  observer.observe(card);
  image.addEventListener('load', alignCard);
  document.fonts.ready.then(alignCard);
  alignCard();
}
