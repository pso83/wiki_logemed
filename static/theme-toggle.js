// theme-toggle.js

function toggleDarkMode() {
    const html = document.documentElement;
    const isDarkNow = html.classList.contains("dark-mode");
    if (isDarkNow) {
        html.classList.remove("dark-mode");
        localStorage.setItem("dark-mode", "false");
    } else {
        html.classList.add("dark-mode");
        localStorage.setItem("dark-mode", "true");
    }
    updateThemeButtonIcon();
}

function updateThemeButtonIcon() {
    const isDark = document.documentElement.classList.contains("dark-mode");
    const btn = document.getElementById("toggle-theme-btn");
    if (btn) btn.textContent = isDark ? "☀️" : "🌙";
}

// Appliquer le thème sombre dès le chargement du HTML
if (localStorage.getItem("dark-mode") === "true") {
    document.documentElement.classList.add("dark-mode");
}

// Dès que le DOM est prêt → met à jour l’icône et active le bouton
document.addEventListener("DOMContentLoaded", function () {
    updateThemeButtonIcon();
    const btn = document.getElementById("toggle-theme-btn");
    if (btn) btn.addEventListener("click", toggleDarkMode);
});
