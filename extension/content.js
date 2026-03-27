// content.js - Injects local search overlay using global event delegation

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

document.addEventListener('focusin', (e) => {
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
    badge = document.createElement('span');
    badge.id = 'local-dl-badge';
    badge.style.background = '#0f8a46'; // Nice Spotify-esque green
    badge.style.color = '#fff';
    badge.style.padding = '4px 8px';
    badge.style.borderRadius = '4px';
    badge.style.fontSize = '13px';
    badge.style.fontWeight = '500';
    badge.style.marginLeft = '12px';
    badge.style.verticalAlign = 'middle';
    badge.style.display = 'inline-block';
    badge.style.boxShadow = '0 2px 4px rgba(0,0,0,0.3)';
  }
  badge.textContent = `☑ Already in Library: ${matchName}`;
  return badge;
}

async function checkCurrentVideo() {
  if (window.location.pathname !== '/watch') {
    const b = document.getElementById('local-dl-badge');
    if(b) b.remove();
    currentVideoTitle = "";
    return;
  }

  // Find YouTube's video title element
  const titleEl = document.querySelector('h1.ytd-watch-metadata yt-formatted-string, h1.title yt-formatted-string, div#title yt-formatted-string, #title > h1');
  
  if (!titleEl) {
      console.log("Local Music Extension: On /watch, but could not find the h1 title element yet.");
      return;
  }
  
  const titleText = titleEl.textContent.trim();
  if (!titleText || titleText === currentVideoTitle) return; // Prevent duplicate checking

  currentVideoTitle = titleText;
  console.log("Local Music Extension: Checking video ->", titleText);
  
  const files = await fetchLocalMatches(titleText);
  
  if (files && files.length > 0) {
    // Inject the success badge into the title container
    const badge = injectBadge(files[0]);
    titleEl.parentElement.appendChild(badge);
  } else {
    const b = document.getElementById('local-dl-badge');
    if(b) b.remove();
  }
}

// YouTube is an aggressive SPA, use a MutationObserver on body to detect page/title changes seamlessly
const observer = new MutationObserver(debounce(checkCurrentVideo, 1000));
observer.observe(document.body, { childList: true, subtree: true });

// Also hook into YouTube's custom navigation events for immediacy
document.addEventListener('yt-navigate-finish', () => setTimeout(checkCurrentVideo, 500));
