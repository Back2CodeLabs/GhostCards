import { useState, useEffect, useCallback } from "react";

/* ------------------------------------------------------------------ */
/* Connexion à l'API                                                    */
/* ------------------------------------------------------------------ */
//
// En déploiement réel (frontend buildé et servi par le même process
// FastAPI que l'API, sur l'OptiPlex), laisser une chaîne vide : les
// appels partent alors vers la même origine, pas de souci de CORS ni de
// contenu mixte.
export const API_BASE = "";

export async function apiGet(path) {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`${res.status} sur ${path}`);
  return res.json();
}

// Le navigateur lève une TypeError avec son propre message quand la requête
// n'atteint même pas le serveur (coupure internet, serveur injoignable) —
// "NetworkError when attempting to fetch resource." sur Firefox, "Failed to
// fetch" sur Chrome/Edge, "Load failed" sur Safari : trois formulations
// techniques en anglais pour la même situation, incompréhensibles pour un
// élève ou un parent. `messageErreur` les remplace par un message clair ;
// une vraie erreur applicative (ex. "Cette adresse n'est pas autorisée...")
// passe telle quelle.
const MESSAGES_RESEAU_BRUTS = /networkerror|failed to fetch|load failed/i;

export function messageErreur(e, secours = "Une erreur est survenue.") {
  const brut = e?.message || "";
  if (MESSAGES_RESEAU_BRUTS.test(brut)) {
    return "Impossible de joindre le serveur — vérifie ta connexion internet.";
  }
  return brut || secours;
}

/* ------------------------------------------------------------------ */
/* Hook générique de récupération API                                   */
/* ------------------------------------------------------------------ */

export function useApi(path, deps = []) {
  // `loaded` (distinct de `data`, qui peut légitimement être null en
  // réponse normale) permet de ne montrer le plein écran "Loading" qu'au
  // tout premier chargement : un `reload()` de fond (polling d'un
  // traitement en cours, par ex.) ne doit pas démonter tout l'écran pour
  // le remplacer par un spinner puis le remonter 5s plus tard — c'est ce
  // qui donnait la sensation de "saut" en haut de page à chaque poll.
  const [state, setState] = useState({ data: null, loading: true, error: null, loaded: false });

  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: !s.loaded, error: null }));
    apiGet(path)
      .then((data) => setState({ data, loading: false, error: null, loaded: true }))
      .catch((e) => setState((s) => ({ ...s, loading: false, error: messageErreur(e, "Impossible de charger les données."), loaded: true })));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    load();
  }, [load]);

  return { ...state, reload: load };
}

/* ------------------------------------------------------------------ */
/* Identité de l'élève connecté (pairage Pronote) — verrouille tout le  */
/* site : voir BackEnd/app/main.py::_require_session.                   */
/* ------------------------------------------------------------------ */

export function useMe() {
  const [state, setState] = useState({ eleve: null, isAdmin: false, loading: true });

  const load = useCallback(() => {
    fetch(`${API_BASE}/api/me`)
      .then((res) => (res.ok ? res.json() : { eleve: null, is_admin: false }))
      .then((data) => setState({ eleve: data.eleve || null, isAdmin: !!data.is_admin, loading: false }))
      .catch(() => setState({ eleve: null, isAdmin: false, loading: false }));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function logout() {
    await fetch(`${API_BASE}/auth/logout`, { method: "POST" });
    setState((s) => ({ ...s, eleve: null }));
  }

  // Pairage Pronote : upload de la capture d'écran du QR code + le PIN à
  // 4 chiffres (voir BackEnd/app/main.py::pairer_eleve_pronote).
  async function pairerPronote(fichierQr, pin) {
    const form = new FormData();
    form.append("qr", fichierQr);
    form.append("pin", pin);
    const res = await fetch(`${API_BASE}/api/eleves/pairage`, { method: "POST", body: form });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Erreur ${res.status}`);
    }
    const data = await res.json();
    await load();
    return data;
  }

  // Connexion admin : mot de passe séparé, totalement indépendant des
  // comptes élèves (Pronote) — voir Services/config.py::ADMIN_PASSWORD.
  async function adminLogin(password) {
    const res = await fetch(`${API_BASE}/auth/admin-login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || `Erreur ${res.status}`);
    }
    setState((s) => ({ ...s, isAdmin: true }));
  }

  async function adminLogout() {
    await fetch(`${API_BASE}/auth/admin-logout`, { method: "POST" });
    setState((s) => ({ ...s, isAdmin: false }));
  }

  return { ...state, reload: load, logout, pairerPronote, adminLogin, adminLogout };
}
