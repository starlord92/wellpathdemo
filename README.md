# Hotkeys Solution — AI Platform Demo Site

A 3D interactive showcase webpage for Hotkeys Solution's three AI products.

## File Structure

```
hotkeys-solution/
├── index.html      # Main page
├── styles.css      # All styles (dark luxury + 3D card effects)
├── app.js          # Three.js 3D background + interactions
└── README.md       # This file
```

## How to Run

### Option 1 — Live Server (Cursor / VS Code)
1. Open the folder in Cursor
2. Right-click `index.html` → **Open with Live Server**
   - Install the "Live Server" extension if you haven't already

### Option 2 — Simple Python Server
```bash
cd hotkeys-solution
python3 -m http.server 3000
# Open http://localhost:3000
```

### Option 3 — Node.js
```bash
npx serve .
```

## Three.js Dependency

The 3D background uses Three.js r128, loaded from CDN:
```
https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js
```

For **fully offline** use:
1. Download the file above
2. Save it as `three.min.js` in this folder
3. Change the script tag in `index.html` from the CDN URL to `./three.min.js`

## Customization

### Colors (`styles.css` → `:root`)
```css
--accent:  #e8ff47   /* Yellow-green — InsightGPT */
--accent2: #47b4ff   /* Blue — Conditional Release */
--accent3: #ff6b47   /* Orange-red — Comp Restore AI */
```

### Products
Edit the three `.product-card` sections in `index.html` to update product names, descriptions, and feature bullets.

### Contact Info
Update the `.contact-info` section in `index.html` with real email/phone.

### 3D Background
Tweak particle count, shape count, and rotation speeds in `app.js`.

## Features
- ✅ Three.js particle field + floating wireframe shapes
- ✅ 3D flip cards for each product (hover to reveal details)
- ✅ Mouse parallax camera movement
- ✅ Scroll-triggered reveal animations
- ✅ Infinite tech stack ticker
- ✅ Contact form with success state
- ✅ Smooth scroll navigation
- ✅ Custom cursor
- ✅ Fully responsive

## Tech Stack
Built with vanilla HTML, CSS, and JavaScript + Three.js. No build step required.
