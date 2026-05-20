/* Script legado para renderizar posiciones GPS en un mapa Leaflet. */

// static/js/tracking.js

document.addEventListener('DOMContentLoaded', function () {
    // Inicializar mapa centrado en Loja, Ecuador
    const map = L.map('map').setView([-4.000, -79.200], 12);

    // Capa base OpenStreetMap (precisa y gratuita)
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
        maxZoom: 18,
    }).addTo(map);

    // Datos pasados desde Flask como JSON seguro
    const locations = JSON.parse(document.getElementById('locations-data').textContent);

    // Añadir marcadores interactivos
    locations.forEach(loc => {
        const marker = L.marker([loc.lat, loc.lon]).addTo(map);
        marker.bindPopup(
            `<b>Bus:</b> ${loc.bus.plate}<br>` +
            `<b>Velocidad:</b> ${loc.speed.toFixed(1)} km/h<br>` +
            `<b>Hora:</b> ${new Date(loc.timestamp).toLocaleString('es-EC')}`
        );
    });

    // Centrar mapa en la primera posición si existe
    if (locations.length > 0) {
        map.setView([locations[0].lat, locations[0].lon], 13);
    }
});