// content.js - Injects local search overlay using global event delegation
//
// =========================================================================
// CRITICAL MEMORY AND RULE:
// THE USER IS NEVER AFK. DO NOT ASSUME THE USER IS ABANDONING THE BROWSER.
// The user rigorously clicks at least 30 times a minute while downloading music.
// This is NOT an AFK issue. Any panel or overlay appearing is a direct bug,
// not a result of native browser inactivity.
// =========================================================================

let overlay = null;

function getOverlay() {
  if (overlay) return overlay;
  overlay = document.createElement('div');
  overlay.id = 'local-music-overlay';
  overlay.style.position = 'absolute';
  overlay.style.background = '#212121';
  overlay.style.color = '#fff';
  overlay.style.border = '1px solid #3d3d3d';
  overlay.style.borderRadius = '8px';
  overlay.style.padding = '8px';
  overlay.style.zIndex = '999999';
  overlay.style.display = 'none';
  overlay.style.boxShadow = '0 4px 12px rgba(0,0,0,0.5)';
  overlay.style.maxHeight = '250px';
  overlay.style.overflowY = 'auto';
  overlay.style.width = '100%';
  overlay.style.top = '100%';
  overlay.style.left = '0';
  overlay.style.marginTop = '4px';
  overlay.style.boxSizing = 'border-box';
  overlay.style.fontFamily = '"Roboto", "Arial", sans-serif';
  return overlay;
}

function debounce(func, wait) {
  let timeout;
  return function(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
}

async function fetchLocalMatches(query) {
  try {
    const res = await fetch(`http://localhost:5005/search?q=${encodeURIComponent(query)}`);
    if (!res.ok) return [];
    return await res.json();
  } catch(e) {
    console.warn("Local Music Extension: Could not reach python API on port 5005.", e.message);
    return null; 
  }
}

async function handleSearchInput(e) {
  const target = e.target;
  if (target.id !== 'search' && target.name !== 'search_query') return;

  const query = target.value.trim();
  const ov = getOverlay();

  if (query.length < 2) {
    ov.style.display = 'none';
    return;
  }

  // Ensure overlay is attached to the wrapper dynamically
  const wrapper = target.closest('ytd-searchbox') || target.parentElement;
  if (wrapper && !wrapper.contains(ov)) {
    wrapper.style.position = 'relative';
    wrapper.appendChild(ov);
  }

  console.log("Local Music Extension: Searching for", query);
  const files = await fetchLocalMatches(query);
  
  if (!files || files.length === 0) {
    ov.style.display = 'none';
    return;
  }

  ov.innerHTML = `
    <div style="font-size: 12px; font-weight: 500; color: #aaa; margin-bottom: 6px; padding-bottom: 6px; border-bottom: 1px solid #3d3d3d; text-transform: uppercase;">
      🎧 Already Downloaded (${files.length})
    </div>
  `;
  
  files.forEach(f => {
    const item = document.createElement('div');
    item.textContent = "✓ " + f;
    item.style.padding = '6px 4px';
    item.style.fontSize = '14px';
    item.style.color = '#3ea6ff';
    item.style.whiteSpace = 'nowrap';
    item.style.overflow = 'hidden';
    item.style.textOverflow = 'ellipsis';
    ov.appendChild(item);
  });
  
  ov.style.display = 'block';
}

const debouncedHandle = debounce(handleSearchInput, 0);

document.addEventListener('input', (e) => {
    if (e.target && (e.target.id === 'search' || e.target.name === 'search_query')) {
        debouncedHandle(e);
    }
}, true);


document.addEventListener('click', (e) => {
  const ov = getOverlay();
  const isSearch = e.target && (e.target.id === 'search' || e.target.name === 'search_query');
  if (!isSearch && !ov.contains(e.target)) {
    ov.style.display = 'none';
  }
});

console.log("🎵 Local Music Sidekick loaded and listening to top-level inputs!");

// --- AUTO-DETECTION ON WATCH PAGES ---
let currentVideoTitle = "";

function injectBadge(matchName) {
  let badge = document.getElementById('local-dl-badge');
  if (!badge) {
    badge = document.createElement('div');
    badge.id = 'local-dl-badge';
    badge.style.background = '#0f8a46'; 
    badge.style.color = '#fff';
    badge.style.padding = '8px 16px';
    badge.style.borderRadius = '30px';
    badge.style.fontSize = '14px';
    badge.style.fontWeight = 'bold';
    badge.style.boxShadow = '0 4px 12px rgba(0,0,0,0.5)';
    badge.style.position = 'fixed';
    badge.style.bottom = '30px';
    badge.style.left = '30px';
    badge.style.zIndex = '999999';
    badge.style.pointerEvents = 'none';
    document.body.appendChild(badge);
  }
  badge.textContent = `☑ Already in Library: ${matchName}`;
  return badge;
}

async function checkCurrentVideo() {

  const ytPopup = document.querySelector('yt-confirm-dialog-renderer');
  if (ytPopup && ytPopup.offsetParent !== null && ytPopup.innerText.includes("watching")) {
      const confirmBtn = document.querySelector('yt-confirm-dialog-renderer #confirm-button, yt-confirm-dialog-renderer [aria-label="Yes"]');
      if (confirmBtn) {
          confirmBtn.click();
          console.log("Local Music Extension: Silently dismissed YouTube native auto-pause prompt.");
      }
  }

  if (window.location.pathname !== '/watch') {
    const b = document.getElementById('local-dl-badge');
    if(b) b.remove();
    currentVideoTitle = "";
    return;
  }

  // Support both modern and legacy/Opera GX YouTube DOM trees
  const titleEl = document.querySelector('h1.ytd-watch-metadata yt-formatted-string, h1.title yt-formatted-string, div#title yt-formatted-string');
  if (!titleEl) return;
  
  const titleText = titleEl.textContent.trim();
  if (!titleText || titleText === currentVideoTitle) return; // Prevent duplicate checking

  currentVideoTitle = titleText;
  console.log("Local Music Extension: Checking video ->", titleText);
  
  const files = await fetchLocalMatches(titleText);
  
  if (files && files.length > 0) {
    injectBadge(files[0]);
  } else {
    const b = document.getElementById('local-dl-badge');
    if(b) b.remove();
  }
}

// YouTube is an aggressive SPA, use a MutationObserver on body to detect page/title changes seamlessly
const observer = new MutationObserver(debounce(checkCurrentVideo, 2000));
observer.observe(document.body, { childList: true, subtree: true });

// Also hook into YouTube's custom navigation events for immediacy
document.addEventListener('yt-navigate-finish', () => setTimeout(checkCurrentVideo, 500));
