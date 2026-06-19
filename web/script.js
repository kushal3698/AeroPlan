// Set to your deployed backend URL (e.g. "https://aeroplan-api.onrender.com") or leave empty "" to use the current host.
const BACKEND_URL = "";

function initApp() {
  // Initialize Lucide Icons
  lucide.createIcons();

  let mapMode = 'leaflet'; // 'leaflet' or 'google'
  let leafletMap;
  let leafletMarkers = [];
  let googleMap;
  let googleMarkers = [];
  let rawItineraryMarkdown = '';

  const googleDarkThemeStyles = [
    { elementType: "geometry", stylers: [{ color: "#172237" }] },
    { elementType: "labels.text.stroke", stylers: [{ color: "#172237" }] },
    { elementType: "labels.text.fill", stylers: [{ color: "#8ba4c9" }] },
    { featureType: "administrative.locality", elementType: "labels.text.fill", stylers: [{ color: "#cbd5e1" }] },
    { featureType: "poi", elementType: "labels.text.fill", stylers: [{ color: "#cbd5e1" }] },
    { featureType: "poi.park", elementType: "geometry", stylers: [{ color: "#111b27" }] },
    { featureType: "poi.park", elementType: "labels.text.fill", stylers: [{ color: "#547990" }] },
    { featureType: "road", elementType: "geometry", stylers: [{ color: "#0f121d" }] },
    { featureType: "road", elementType: "geometry.stroke", stylers: [{ color: "#1e293b" }] },
    { featureType: "road", elementType: "labels.text.fill", stylers: [{ color: "#64748b" }] },
    { featureType: "road.highway", elementType: "geometry", stylers: [{ color: "#1e293b" }] },
    { featureType: "road.highway", elementType: "geometry.stroke", stylers: [{ color: "#334155" }] },
    { featureType: "water", elementType: "geometry", stylers: [{ color: "#0f172a" }] },
    { featureType: "water", elementType: "labels.text.fill", stylers: [{ color: "#38bdf8" }] }
  ];

  // Initialize Leaflet Map
  function initLeaflet() {
    mapMode = 'leaflet';
    const mapModeBadge = document.getElementById('map-mode-badge');
    if (mapModeBadge) mapModeBadge.textContent = 'Leaflet Fallback';
    
    try {
      leafletMap = L.map('map').setView([35.0116, 135.7681], 12);
      L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
        attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
      }).addTo(leafletMap);
    } catch (e) {
      console.error("Leaflet initialization failed:", e);
    }
  }

  // Initialize Google Map callback
  window.initGoogleMap = async function() {
    mapMode = 'google';
    const mapModeBadge = document.getElementById('map-mode-badge');
    if (mapModeBadge) {
      mapModeBadge.textContent = 'Google Maps';
      mapModeBadge.style.background = 'rgba(16, 185, 129, 0.2)';
      mapModeBadge.style.color = '#10b981';
      mapModeBadge.style.borderColor = 'rgba(16, 185, 129, 0.3)';
    }

    try {
      const { Map } = await google.maps.importLibrary("maps");
      googleMap = new Map(document.getElementById("map"), {
        zoom: 12,
        center: { lat: 35.0116, lng: 135.7681 },
        styles: googleDarkThemeStyles,
        disableDefaultUI: false,
        mapTypeControl: false,
        mapId: "f8b9e6163e48e501"
      });
      console.log("Google Map initialized successfully.");
    } catch (e) {
      console.error("Google Map initialization failed, falling back to Leaflet:", e);
      initLeaflet();
    }
  };

  // Update Map function
  async function updateMap(dest) {
    if (mapMode === 'google' && typeof google !== 'undefined') {
      try {
        const { Geocoder } = await google.maps.importLibrary("geocoding").catch(() => google.maps);
        const { AdvancedMarkerElement } = await google.maps.importLibrary("marker");
        const geocoder = new google.maps.Geocoder();
        geocoder.geocode({ address: dest }, (results, status) => {
          if (status === "OK" && results[0]) {
            const loc = results[0].geometry.location;
            googleMap.setCenter(loc);
            googleMap.setZoom(13);
            
            // Clear old markers
            googleMarkers.forEach(m => m.map = null);
            googleMarkers = [];
            
            let mainMarker = new AdvancedMarkerElement({
              position: loc,
              map: googleMap,
              title: dest
            });
            googleMarkers.push(mainMarker);
            
            if (dest.toLowerCase().includes("kyoto")) {
              const attractions = [
                { name: "Fushimi Inari Shrine (\u0c2b\u0c41\u0c37\u0c3f\u0c2e\u0c3f \u0c07\u0c28\u0c3e\u0c30\u0c3f)", lat: 34.9671, lng: 135.7727 },
                { name: "Kinkaku-ji Golden Pavilion (\u0c15\u0c3f\u0c02\u0c15\u0c3e\u0c15\u0c41-\u0c1c\u0c3f)", lat: 35.0394, lng: 135.7292 },
                { name: "Arashiyama Bamboo Grove (\u0c05\u0c30\u0c3e\u0c37\u0c3f\u0c2f\u0c3e\u0c2e\u0c3e)", lat: 35.0156, lng: 135.6715 },
                { name: "Kiyomizu-dera (\u0c15\u0c3f\u0c2f\u0c4b\u0c2e\ి\u0c1c\u0c41-\u0c26\u0c47\u0c30\u0c3e)", lat: 34.9949, lng: 135.7850 }
              ];
              
              const bounds = new google.maps.LatLngBounds();
              bounds.extend(loc);
              
              attractions.forEach(attr => {
                let pos = { lat: attr.lat, lng: attr.lng };
                let m = new AdvancedMarkerElement({
                  position: pos,
                  map: googleMap,
                  title: attr.name
                });
                googleMarkers.push(m);
                bounds.extend(pos);
              });
              
              googleMap.fitBounds(bounds);
            }
          } else {
            console.warn("Google Geocoding failed, trying Leaflet geocoding fallback.");
            updateLeafletMap(dest);
          }
        });
      } catch (err) {
        console.error("Google Geocoding error, falling back:", err);
        updateLeafletMap(dest);
      }
    } else {
      updateLeafletMap(dest);
    }
  }

  // Update Leaflet Map function
  async function updateLeafletMap(dest) {
    if (!leafletMap) return;
    
    let lat = 35.0116;
    let lon = 135.7681;
    let zoomLevel = 12;
    
    try {
      const resp = await fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(dest)}`);
      const data = await resp.json();
      if (data && data.length > 0) {
        lat = parseFloat(data[0].lat);
        lon = parseFloat(data[0].lon);
        zoomLevel = 13;
      }
    } catch(e) {
      console.error("Geocoding failed, using defaults:", e);
    }
    
    // Clear old markers
    leafletMarkers.forEach(m => leafletMap.removeLayer(m));
    leafletMarkers = [];
    
    leafletMap.setView([lat, lon], zoomLevel);
    
    let mainMarker = L.marker([lat, lon]).addTo(leafletMap)
      .bindPopup(`<b>${dest}</b>`)
      .openPopup();
    leafletMarkers.push(mainMarker);
    
    if (dest.toLowerCase().includes("kyoto")) {
      const attractions = [
        { name: "Fushimi Inari Shrine (\u0c2b\u0c41\u0c37\u0c3f\u0c2e\u0c3f \u0c07\u0c28\u0c3e\u0c30\u0c3f)", coords: [34.9671, 135.7727] },
        { name: "Kinkaku-ji Golden Pavilion (\u0c15\u0c3f\u0c02\u0c15\u0c3e\u0c15\u0c41-\u0c1c\u0c3f)", coords: [35.0394, 135.7292] },
        { name: "Arashiyama Bamboo Grove (\u0c05\u0c30\u0c3e\u0c37\u0c3f\u0c2f\u0c3e\u0c2e\u0c3e)", coords: [35.0156, 135.6715] },
        { name: "Kiyomizu-dera (\u0c15\u0c3f\u0c2f\u0c4b\u0c2e\u0c3f\u0c1c\u0c41-\u0c26\u0c47\u0c30\u0c3e)", coords: [34.9949, 135.7850] }
      ];
      
      attractions.forEach(attr => {
        let m = L.marker(attr.coords).addTo(leafletMap)
          .bindPopup(`<b>${attr.name}</b>`);
        leafletMarkers.push(m);
      });
      
      let group = new L.featureGroup(leafletMarkers);
      leafletMap.fitBounds(group.getBounds().pad(0.1));
    }
  }


  const form = document.getElementById('planner-form');
  const submitBtn = document.getElementById('submit-btn');
  const customInterestInput = document.getElementById('custom-interest');
  const addInterestBtn = document.getElementById('add-interest-btn');
  const interestsContainer = document.getElementById('interests-container');
  const statusLabel = document.querySelector('.status-label');
  const apiStatus = document.getElementById('api-status');

  // Tab Elements
  const tabButtons = document.querySelectorAll('.tab-btn');
  const tabContents = document.querySelectorAll('.tab-content');

  // Workflow Graph Nodes & Arrows
  const nodeStart = document.getElementById('node-start');
  const nodeResearcher = document.getElementById('node-researcher');
  const nodeBudget = document.getElementById('node-budget');
  const nodePlanner = document.getElementById('node-planner');
  const nodeEnd = document.getElementById('node-end');

  const arrow1 = document.getElementById('arrow-1');
  const arrow2 = document.getElementById('arrow-2');
  const arrow3 = document.getElementById('arrow-3');
  const arrow4 = document.getElementById('arrow-4');

  // Outputs Placeholders & Render Containers
  const itineraryPlaceholder = document.getElementById('itinerary-placeholder');
  const itineraryRendered = document.getElementById('itinerary-rendered');
  const researchPlaceholder = document.getElementById('research-placeholder');
  const researchRendered = document.getElementById('research-rendered');
  const budgetPlaceholder = document.getElementById('budget-placeholder');
  const budgetRendered = document.getElementById('budget-rendered');

  // Execution Banner
  const execBanner = document.getElementById('execution-status-banner');
  const execText = document.getElementById('execution-status-text');

  // Check backend configuration
  fetch(BACKEND_URL + '/api/config')
    .then(res => res.json())
    .then(data => {
      if (!data.is_mock) {
        apiStatus.classList.add('live');
        statusLabel.textContent = 'Live Mode (OpenAI)';
      } else {
        apiStatus.classList.remove('live');
        statusLabel.textContent = 'Simulation Mode';
      }

      // Load Google Maps API if key exists, otherwise fall back to Leaflet
      if (data.google_maps_api_key && data.google_maps_api_key.trim() && !data.google_maps_api_key.startsWith("your_")) {
        console.log("Google Maps API Key found, loading Google Maps via modern dynamic loader...");
        (g=>{var h,a,k,p="The Google Maps JavaScript API",c="google",l="importLibrary",q="__ib__",m=document,b=window;b=b[c]||(b[c]={});var d=b.maps||(b.maps={}),r=new Set,e=new URLSearchParams,u=()=>h||(h=new Promise(async(f,n)=>{await (a=m.createElement("script"));e.set("libraries",[...r]+"");for(k in g)e.set(k.replace(/[A-Z]/g,t=>"_"+t[0].toLowerCase()),g[k]);e.set("callback",c+".maps."+q);a.src=`https://maps.${c}apis.com/maps/api/js?`+e;d[q]=f;a.onerror=()=>h=n(Error(p+" could not load."));a.nonce=m.querySelector("script[nonce]")?.nonce||"";m.head.append(a)}));d[l]?console.warn(p+" only loads once. Ignoring:",g):d[l]=(f,...n)=>r.add(f)&&u().then(()=>d[l](f,...n))})
        ({
          key: data.google_maps_api_key,
          v: "weekly"
        });
        
        // Trigger initialization
        initGoogleMap();
      } else {
        console.log("No Google Maps API Key found. Using Leaflet fallback.");
        initLeaflet();
      }
    })
    .catch(() => {
      statusLabel.textContent = 'Offline';
      initLeaflet();
    });

  // Tab Switch Handler
  tabButtons.forEach(btn => {
    btn.addEventListener('click', () => {
      const tabId = btn.getAttribute('data-tab');
      
      tabButtons.forEach(b => b.classList.remove('active'));
      tabContents.forEach(c => c.classList.remove('active'));
      
      btn.classList.add('active');
      document.getElementById(tabId).classList.add('active');
    });
  });

  // Activate a specific tab
  function activateTab(tabId) {
    tabButtons.forEach(b => {
      if (b.getAttribute('data-tab') === tabId) {
        b.classList.add('active');
      } else {
        b.classList.remove('active');
      }
    });
    tabContents.forEach(c => {
      if (c.id === tabId) {
        c.classList.add('active');
      } else {
        c.classList.remove('active');
      }
    });
  }

  // Add Custom Interest Tag
  addInterestBtn.addEventListener('click', () => {
    const val = customInterestInput.value.trim();
    if (val) {
      const id = 'int-' + Date.now();
      const tagDiv = document.createElement('div');
      tagDiv.className = 'tag-checkbox';
      tagDiv.innerHTML = `
        <input type="checkbox" id="${id}" value="${val}" checked>
        <label for="${id}">\u2708\ufe0f ${val}</label>
      `;
      interestsContainer.appendChild(tagDiv);
      customInterestInput.value = '';
    }
  });

  customInterestInput.addEventListener('keypress', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      addInterestBtn.click();
    }
  });

  // Export PDF click handler - utilizes native browser printing with CSS print media overrides
  const exportPdfBtn = document.getElementById('export-pdf-btn');
  if (exportPdfBtn) {
    exportPdfBtn.addEventListener('click', () => {
      window.print();
    });
  }

  // Export ICS calendar click handler
  const exportIcsBtn = document.getElementById('export-ics-btn');
  if (exportIcsBtn) {
    exportIcsBtn.addEventListener('click', () => {
      if (!rawItineraryMarkdown) {
        alert('No itinerary available to export!');
        return;
      }
      const destination = document.getElementById('destination').value || 'Destination';
      const icsString = generateICS(destination, rawItineraryMarkdown);
      if (!icsString) {
        alert('Failed to parse itinerary events.');
        return;
      }
      
      const blob = new Blob([icsString], { type: 'text/calendar;charset=utf-8' });
      const link = document.createElement('a');
      link.href = window.URL.createObjectURL(blob);
      link.download = `${destination.replace(/[^a-z0-9]/gi, '_').toLowerCase()}_calendar.ics`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    });
  }

  // Parse Markdown itinerary into an ICS format
  function generateICS(destination, text) {
    const lines = text.split('\n');
    let currentDay = '';
    let events = [];
    
    for (let line of lines) {
      line = line.trim();
      const dayMatch = line.match(/^##\s+(Day\s+\d+[:\-\s]*.*)/i);
      if (dayMatch) {
        currentDay = dayMatch[1];
        continue;
      }
      
      const itemMatch = line.match(/^-\s+(.*)/);
      if (itemMatch && currentDay) {
        let content = itemMatch[1].replace(/\*\*/g, '').trim();
        events.push({
          day: currentDay,
          summary: content
        });
      }
    }
    
    if (events.length === 0) {
      const days = text.match(/##\s+Day\s+\d+[:\-\s]*[^\n]+/gi) || [];
      if (days.length > 0) {
        days.forEach((day, idx) => {
          const dayTitle = day.replace(/^##\s+/, '');
          events.push({
            day: dayTitle,
            summary: `Explore ${destination} - ${dayTitle}`
          });
        });
      } else {
        events.push({
          day: 'Day 1',
          summary: `Trip to ${destination}`
        });
      }
    }
    
    let icsContent = [
      'BEGIN:VCALENDAR',
      'VERSION:2.0',
      'PRODID:-//AeroPlan//Travel Itinerary//EN',
      'CALSCALE:GREGORIAN',
      'METHOD:PUBLISH'
    ];
    
    const now = new Date();
    const nowStr = now.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
    const startDate = new Date();
    startDate.setDate(startDate.getDate() + 1); // Starts tomorrow
    
    events.forEach((evt, idx) => {
      const dayNumMatch = evt.day.match(/Day\s+(\d+)/i);
      const dayOffset = dayNumMatch ? parseInt(dayNumMatch[1]) - 1 : 0;
      
      const eventDate = new Date(startDate);
      eventDate.setDate(startDate.getDate() + dayOffset);
      
      const dateStr = eventDate.toISOString().split('T')[0].replace(/-/g, '');
      let timeMatch = evt.summary.match(/^(\d{1,2}):(\d{2})\s*(AM|PM)/i);
      let summaryText = evt.summary;
      let startHour = 9 + (idx % 6); // default staggered
      let startMin = 0;
      
      if (timeMatch) {
        let hr = parseInt(timeMatch[1]);
        let min = parseInt(timeMatch[2]);
        let ampm = timeMatch[3].toUpperCase();
        if (ampm === 'PM' && hr < 12) hr += 12;
        if (ampm === 'AM' && hr === 12) hr = 0;
        startHour = hr;
        startMin = min;
        summaryText = evt.summary.replace(/^.*?:\s*/, '');
      }
      
      eventDate.setHours(startHour, startMin, 0);
      const startStr = eventDate.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
      
      const endEventDate = new Date(eventDate);
      endEventDate.setHours(startHour + 1);
      const endStr = endEventDate.toISOString().replace(/[-:]/g, '').split('.')[0] + 'Z';
      
      const uid = `aeroplan_${dateStr}_${idx}_${Date.now()}@kushal3698.github.io`;
      
      icsContent.push('BEGIN:VEVENT');
      icsContent.push(`UID:${uid}`);
      icsContent.push(`DTSTAMP:${nowStr}`);
      icsContent.push(`DTSTART:${startStr}`);
      icsContent.push(`DTEND:${endStr}`);
      icsContent.push(`SUMMARY:${summaryText} (${destination})`);
      icsContent.push(`DESCRIPTION:${evt.day}: ${evt.summary} - Planned by AeroPlan AI`);
      icsContent.push(`LOCATION:${destination}`);
      icsContent.push('END:VEVENT');
    });
    
    icsContent.push('END:VCALENDAR');
    return icsContent.join('\r\n');
  }

  // Reset Graph Node States
  function resetGraph() {
    const nodes = [nodeStart, nodeResearcher, nodeBudget, nodePlanner, nodeEnd];
    nodes.forEach(n => {
      n.classList.remove('active', 'completed');
      const statusText = n.querySelector('.node-status');
      if (statusText) statusText.textContent = 'Idle';
    });

    const arrows = [arrow1, arrow2, arrow3, arrow4];
    arrows.forEach(a => a.classList.remove('active'));

    execBanner.classList.remove('running');
  }

  // Handle Form Submit
  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    // Disable submit button
    submitBtn.disabled = true;
    resetGraph();

    // Clear previous outputs
    itineraryRendered.innerHTML = '';
    itineraryPlaceholder.style.display = 'flex';
    researchRendered.innerHTML = '';
    researchPlaceholder.style.display = 'flex';
    budgetRendered.innerHTML = '';
    budgetPlaceholder.style.display = 'flex';

    const actionsDiv = document.getElementById('itinerary-actions');
    if (actionsDiv) {
      actionsDiv.style.display = 'none';
    }

    // Collect form values
    const destination = document.getElementById('destination').value;
    updateMap(destination);
    const duration_days = parseInt(document.getElementById('duration').value);
    const budget_limit = parseFloat(document.getElementById('budget').value);
    const currency = document.getElementById('currency').value;
    const language = document.getElementById('language').value;
    
    // Collect checked interests
    const interests = [];
    interestsContainer.querySelectorAll('input[type="checkbox"]').forEach(cb => {
      if (cb.checked) {
        interests.push(cb.value);
      }
    });

    // Update banner to running state
    execBanner.classList.add('running');
    execText.textContent = `Initializing travel agent workflow (${language} / ${currency})...`;

    // Highlight START node
    nodeStart.classList.add('completed');
    arrow1.classList.add('active');

    try {
      const response = await fetch(BACKEND_URL + '/api/plan', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          destination,
          duration_days,
          interests,
          budget_limit,
          currency,
          language
        })
      });

      if (!response.ok) {
        throw new Error('Failed to initiate trip planning.');
      }

      // Read SSE stream
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value);
        const lines = buffer.split('\n\n');
        buffer = lines.pop(); // Keep last potentially partial line in buffer

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              handleAgentEvent(data);
            } catch (err) {
              console.error('Error parsing SSE data:', err);
            }
          }
        }
      }

    } catch (err) {
      execBanner.classList.remove('running');
      execText.textContent = 'Error: ' + err.message;
      submitBtn.disabled = false;
    }
  });

  // Handle Graph and Tab updates based on incoming agent events
  function handleAgentEvent(data) {
    switch(data.event) {
      case 'start':
        execText.textContent = data.message;
        break;

      case 'node_start':
        updateNodeState(data.node, 'active');
        break;

      case 'node_complete':
        updateNodeState(data.node, 'completed');
        displayNodeOutput(data.node, data.data);
        break;

      case 'end':
        execBanner.classList.remove('running');
        execText.textContent = data.message;
        nodeEnd.classList.add('completed');
        submitBtn.disabled = false;
        
        // Return tab focus back to itinerary
        activateTab('tab-itinerary');

        const actionsDiv = document.getElementById('itinerary-actions');
        if (actionsDiv) {
          actionsDiv.style.display = 'flex';
        }
        break;

      case 'error':
        execBanner.classList.remove('running');
        execText.textContent = 'Workflow error: ' + data.message;
        submitBtn.disabled = false;
        break;
    }
  }

  // Update Graph Visual States
  function updateNodeState(node, state) {
    if (node === 'researcher') {
      if (state === 'active') {
        nodeResearcher.classList.add('active');
        nodeResearcher.querySelector('.node-status').textContent = 'Analyzing...';
        execText.textContent = 'Travel Researcher is collecting highlights and dining options...';
      } else if (state === 'completed') {
        nodeResearcher.classList.remove('active');
        nodeResearcher.classList.add('completed');
        nodeResearcher.querySelector('.node-status').textContent = 'Completed';
        arrow2.classList.add('active');
      }
    } 
    else if (node === 'budget') {
      if (state === 'active') {
        nodeBudget.classList.add('active');
        nodeBudget.querySelector('.node-status').textContent = 'Calculating...';
        execText.textContent = 'Budget Manager is estimating accommodation, meals, and transit...';
      } else if (state === 'completed') {
        nodeBudget.classList.remove('active');
        nodeBudget.classList.add('completed');
        nodeBudget.querySelector('.node-status').textContent = 'Completed';
        arrow3.classList.add('active');
      }
    } 
    else if (node === 'planner') {
      if (state === 'active') {
        nodePlanner.classList.add('active');
        nodePlanner.querySelector('.node-status').textContent = 'Structuring...';
        execText.textContent = 'Itinerary Planner is organizing your day-by-day schedule...';
      } else if (state === 'completed') {
        nodePlanner.classList.remove('active');
        nodePlanner.classList.add('completed');
        nodePlanner.querySelector('.node-status').textContent = 'Completed';
        arrow4.classList.add('active');
      }
    }
  }

  // Render markdown outputs to respective tabs and auto-switch focus
  function displayNodeOutput(node, data) {
    if (node === 'researcher') {
      const notes = data.research_notes;
      researchPlaceholder.style.display = 'none';
      researchRendered.innerHTML = marked.parse(notes);
      activateTab('tab-research');
    } 
    else if (node === 'budget') {
      const budget = data.budget_notes;
      budgetPlaceholder.style.display = 'none';
      budgetRendered.innerHTML = marked.parse(budget);
      activateTab('tab-budget');
    } 
    else if (node === 'planner') {
      const itinerary = data.final_itinerary;
      rawItineraryMarkdown = itinerary;
      itineraryPlaceholder.style.display = 'none';
      itineraryRendered.innerHTML = marked.parse(itinerary);
      activateTab('tab-itinerary');
    }
  }

  // Handle window resize to invalidate leaflet map size dynamically
  window.addEventListener('resize', () => {
    if (mapMode === 'leaflet' && leafletMap) {
      leafletMap.invalidateSize();
    }
  });
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initApp);
} else {
  initApp();
}
