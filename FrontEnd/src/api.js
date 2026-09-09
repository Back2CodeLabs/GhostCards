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

/* ------------------------------------------------------------------ */
/* Hook générique de récupération API                                   */
/* ------------------------------------------------------------------ */

export function useApi(path, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null });

  const load = useCallback(() => {
    setState((s) => ({ ...s, loading: true, error: null }));
    apiGet(path)
      .then((data) => setState({ data, loading: false, error: null }))
      .catch((e) => setState({ data: null, loading: false, error: e.message }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  useEffect(() => {
    load();
  }, [load]);

  return { ...state, reload: load };
}

/* ------------------------------------------------------------------ */
/* Identité de l'élève connecté (Google) — sert uniquement à attribuer  */
/* les notes déposées ; la consultation du site reste libre.            */
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

  // Connexion admin : mot de passe séparé, totalement indépendant des
  // comptes élèves (Google) — voir Services/config.py::ADMIN_PASSWORD.
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

  return { ...state, reload: load, logout, adminLogin, adminLogout };
}
