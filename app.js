/* ============================================================
   HOTKEYS SOLUTION — APP.JS
   Three.js 3D background + interactions
   ============================================================ */

// ---- Custom Cursor ----
document.addEventListener('mousemove', (e) => {
  document.documentElement.style.setProperty('--mx', e.clientX + 'px');
  document.documentElement.style.setProperty('--my', e.clientY + 'px');
});

// ---- Form Submit ----
function handleSubmit(e) {
  e.preventDefault();
  document.querySelector('.contact-form').style.display = 'none';
  document.getElementById('form-success').style.display = 'flex';
}

// ---- Intersection Observer for reveal animations ----
const revealEls = document.querySelectorAll('.product-card, .contact-grid, .section-title, .section-label');
revealEls.forEach(el => el.classList.add('reveal'));

const observer = new IntersectionObserver((entries) => {
  entries.forEach((entry, i) => {
    if (entry.isIntersecting) {
      setTimeout(() => entry.target.classList.add('visible'), i * 100);
      observer.unobserve(entry.target);
    }
  });
}, { threshold: 0.1 });

revealEls.forEach(el => observer.observe(el));

// ---- Three.js 3D Background ----
(function () {
  const canvas = document.getElementById('bg-canvas');
  if (!canvas || typeof THREE === 'undefined') return;

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(window.innerWidth, window.innerHeight);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 1000);
  camera.position.set(0, 0, 30);

  // Responsive
  window.addEventListener('resize', () => {
    renderer.setSize(window.innerWidth, window.innerHeight);
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
  });

  // ---- Grid of points ----
  const pointsGeometry = new THREE.BufferGeometry();
  const count = 2000;
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);

  const palette = [
    new THREE.Color('#e8ff47'),
    new THREE.Color('#47b4ff'),
    new THREE.Color('#ff6b47'),
    new THREE.Color('#ffffff'),
  ];

  for (let i = 0; i < count; i++) {
    positions[i * 3]     = (Math.random() - 0.5) * 80;
    positions[i * 3 + 1] = (Math.random() - 0.5) * 80;
    positions[i * 3 + 2] = (Math.random() - 0.5) * 40;

    const c = palette[Math.floor(Math.random() * palette.length)];
    const brightness = Math.random() * 0.3 + 0.05;
    colors[i * 3]     = c.r * brightness;
    colors[i * 3 + 1] = c.g * brightness;
    colors[i * 3 + 2] = c.b * brightness;
  }

  pointsGeometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
  pointsGeometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

  const pointsMaterial = new THREE.PointsMaterial({
    size: 0.15,
    vertexColors: true,
    transparent: true,
    opacity: 0.8,
    sizeAttenuation: true,
  });

  const pointsMesh = new THREE.Points(pointsGeometry, pointsMaterial);
  scene.add(pointsMesh);

  // ---- Wireframe floating shapes ----
  const shapes = [];
  const shapeDefs = [
    { geo: new THREE.OctahedronGeometry(3, 0), pos: [15, 10, -5], color: '#e8ff47' },
    { geo: new THREE.IcosahedronGeometry(2, 0), pos: [-12, -8, -3], color: '#47b4ff' },
    { geo: new THREE.TetrahedronGeometry(2.5, 0), pos: [8, -12, 2], color: '#ff6b47' },
    { geo: new THREE.OctahedronGeometry(1.5, 0), pos: [-18, 5, -8], color: '#ffffff' },
    { geo: new THREE.IcosahedronGeometry(1.2, 0), pos: [20, -5, -10], color: '#e8ff47' },
  ];

  shapeDefs.forEach(({ geo, pos, color }) => {
    const mat = new THREE.MeshBasicMaterial({
      color,
      wireframe: true,
      transparent: true,
      opacity: 0.08,
    });
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(...pos);
    mesh.userData.rotSpeed = {
      x: (Math.random() - 0.5) * 0.003,
      y: (Math.random() - 0.5) * 0.005,
      z: (Math.random() - 0.5) * 0.002,
    };
    scene.add(mesh);
    shapes.push(mesh);
  });

  // ---- Connecting lines (grid) ----
  const gridGeometry = new THREE.BufferGeometry();
  const gridLines = [];
  const lineCount = 30;
  for (let i = 0; i < lineCount; i++) {
    const x = (i / lineCount) * 80 - 40;
    gridLines.push(x, -40, -15, x, 40, -15);
  }
  for (let i = 0; i < lineCount; i++) {
    const y = (i / lineCount) * 80 - 40;
    gridLines.push(-40, y, -15, 40, y, -15);
  }

  gridGeometry.setAttribute('position', new THREE.BufferAttribute(new Float32Array(gridLines), 3));
  const gridMat = new THREE.LineBasicMaterial({ color: '#1a1c1e', transparent: true, opacity: 0.5 });
  const gridMesh = new THREE.LineSegments(gridGeometry, gridMat);
  scene.add(gridMesh);

  // ---- Mouse parallax ----
  let mouseX = 0, mouseY = 0;
  document.addEventListener('mousemove', (e) => {
    mouseX = (e.clientX / window.innerWidth - 0.5) * 2;
    mouseY = (e.clientY / window.innerHeight - 0.5) * 2;
  });

  // ---- Scroll parallax ----
  let scrollY = 0;
  window.addEventListener('scroll', () => { scrollY = window.scrollY; });

  // ---- Animate ----
  const clock = new THREE.Clock();

  function animate() {
    requestAnimationFrame(animate);
    const t = clock.getElapsedTime();

    // Points slow rotation
    pointsMesh.rotation.y = t * 0.02;
    pointsMesh.rotation.x = t * 0.008;

    // Shape rotations
    shapes.forEach(s => {
      s.rotation.x += s.userData.rotSpeed.x;
      s.rotation.y += s.userData.rotSpeed.y;
      s.rotation.z += s.userData.rotSpeed.z;
    });

    // Camera mouse parallax
    camera.position.x += (mouseX * 3 - camera.position.x) * 0.04;
    camera.position.y += (-mouseY * 2 - camera.position.y) * 0.04;
    camera.position.z = 30 + scrollY * 0.005;
    camera.lookAt(0, 0, 0);

    renderer.render(scene, camera);
  }

  animate();
})();

// ---- Card flip (3 sec hover or click) + tilt ----
document.querySelectorAll('.product-card').forEach(card => {
  let flipTimer = null;

  function flipCard() {
    card.classList.add('flipped');
    const inner = card.querySelector('.card-inner');
    inner.style.transform = 'rotateY(180deg)';
  }

  function unflipCard() {
    card.classList.remove('flipped');
    const inner = card.querySelector('.card-inner');
    inner.style.transition = 'transform 0.8s cubic-bezier(0.4,0,0.2,1)';
    inner.style.transform = '';
  }

  card.addEventListener('mouseenter', () => {
    flipTimer = setTimeout(flipCard, 3000);
  });

  card.addEventListener('mouseleave', () => {
    if (flipTimer) {
      clearTimeout(flipTimer);
      flipTimer = null;
    }
    unflipCard();
  });

  // Click to flip (for touch devices + quick flip)
  card.addEventListener('click', (e) => {
    if (e.target.closest('a')) return; // Don't flip when clicking links
    if (flipTimer) {
      clearTimeout(flipTimer);
      flipTimer = null;
    }
    card.classList.toggle('flipped');
    const inner = card.querySelector('.card-inner');
    if (card.classList.contains('flipped')) {
      inner.style.transform = 'rotateY(180deg)';
    } else {
      inner.style.transition = 'transform 0.8s cubic-bezier(0.4,0,0.2,1)';
      inner.style.transform = '';
    }
  });

  card.addEventListener('mousemove', (e) => {
    const rect = card.getBoundingClientRect();
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    const dx = (e.clientX - cx) / (rect.width / 2);
    const dy = (e.clientY - cy) / (rect.height / 2);

    const inner = card.querySelector('.card-inner');
    const cardBack = card.querySelector('.card-back');
    const isOverBackFace = cardBack && cardBack.contains(e.target);

    inner.style.transition = 'transform 0.1s';
    if (isOverBackFace && card.classList.contains('flipped')) {
      inner.style.transform = 'rotateY(180deg)';
    } else if (!card.classList.contains('flipped')) {
      inner.style.transform =
        `rotateY(${dx * 10}deg) rotateX(${-dy * 8}deg)`;
    }
  });
});

// ---- Smooth nav link scroll ----
document.querySelectorAll('a[href^="#"]').forEach(a => {
  a.addEventListener('click', (e) => {
    const target = document.querySelector(a.getAttribute('href'));
    if (target) {
      e.preventDefault();
      target.scrollIntoView({ behavior: 'smooth' });
    }
  });
});

console.log('%c[HK] HOTKEYS SOLUTION', 'color:#e8ff47;font-size:16px;font-weight:bold;');
console.log('%cAI Platform Demo — Built with precision.', 'color:#666;font-size:12px;');
