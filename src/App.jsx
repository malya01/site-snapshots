import { useEffect, useState } from "react";
import { api } from "./api";

const TEST_URL =
  "https://www.justdial.com/Hyderabad/Dr-Sarita-Rao-Tx-Hospitals-Near-Masjid-Uppal-Bus-Stand-Bharath-Nagar-Colony-Uppal/040PXX40-XX40-231215200040-Y2E1_BZDET";

export default function App() {
  const [session, setSession] = useState(() => {
    try { return JSON.parse(localStorage.getItem("session")); } catch { return null; }
  });

  const save = (s) => {
    s ? localStorage.setItem("session", JSON.stringify(s)) : localStorage.removeItem("session");
    setSession(s);
  };

  return session
    ? <Dashboard session={session} onLogout={() => save(null)} />
    : <Auth onAuth={save} />;
}

function Auth({ onAuth }) {
  const [mode, setMode] = useState("login");
  const [form, setForm] = useState({ email: "", password: "" });
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setBusy(true);
    try { onAuth(await api(`/${mode}`, { method: "POST", body: form })); }
    catch (err) { setError(err.message); }
    finally { setBusy(false); }
  };

  const isLogin = mode === "login";
  return (
    <main className="auth">
      <h1>Site Snapshots</h1>
      <p className="lede">Save any web page with a picture of how it looked.</p>
      <form onSubmit={submit}>
        <label>Email
          <input type="email" required autoComplete="email" value={form.email}
                 onChange={(e) => setForm({ ...form, email: e.target.value })} />
        </label>
        <label>Password
          <input type="password" required minLength={6}
                 autoComplete={isLogin ? "current-password" : "new-password"} value={form.password}
                 onChange={(e) => setForm({ ...form, password: e.target.value })} />
        </label>
        {error && <p className="error" role="alert">{error}</p>}
        <button disabled={busy}>{busy ? "Please wait…" : isLogin ? "Log in" : "Create account"}</button>
      </form>
      <p className="switch">
        {isLogin ? "New here?" : "Already have an account?"}{" "}
        <button className="link" onClick={() => { setMode(isLogin ? "signup" : "login"); setError(""); }}>
          {isLogin ? "Create an account" : "Log in"}
        </button>
      </p>
    </main>
  );
}

function Dashboard({ session, onLogout }) {
  const { token, email } = session;
  const [items, setItems] = useState(null);
  const [url, setUrl] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const fail = (err) => (err.status === 401 ? onLogout() : setError(err.message));

  useEffect(() => {
    api("/previews", { token }).then(setItems).catch(fail);
  }, []);

  const submit = async (e) => {
    e.preventDefault();
    setError(""); setBusy(true);
    try {
      const item = await api("/previews", { method: "POST", body: { url }, token });
      setItems((prev) => [item, ...(prev || [])]);
      setUrl("");
    } catch (err) { fail(err); }
    finally { setBusy(false); }
  };

  return (
    <>
      <header className="top">
        <strong>Site Snapshots</strong>
        <span>{email} <button className="link" onClick={onLogout}>Log out</button></span>
      </header>
      <main className="dash">
        <form className="add" onSubmit={submit}>
          <input type="url" required placeholder="https://example.com" value={url}
                 onChange={(e) => setUrl(e.target.value)} aria-label="Website URL" />
          <button disabled={busy}>{busy ? "Capturing…" : "Save snapshot"}</button>
        </form>
        <p className="hint">
          {busy ? "Loading the page and taking a screenshot. This can take up to 30 seconds."
                : <>No URL handy? <button className="link" type="button" onClick={() => setUrl(TEST_URL)}>Use the test URL</button></>}
        </p>
        {error && <p className="error" role="alert">{error}</p>}

        {items === null ? <p className="hint">Loading your snapshots…</p>
          : items.length === 0 ? <p className="empty">Nothing saved yet. Paste a URL above to save your first snapshot.</p>
          : <ul className="grid">{items.map((i) => <Card key={i.id} item={i} />)}</ul>}
      </main>
    </>
  );
}

function Card({ item }) {
  return (
    <li className="win">
      <div className="chrome">
        <i /><i /><i />
        <a href={item.url} target="_blank" rel="noreferrer" title={item.url}>{item.url}</a>
      </div>
      {item.image
        ? <img src={item.image} alt={`Preview of ${item.title || item.url}`} loading="lazy" />
        : <div className="noimg">Preview unavailable for this site</div>}
      <div className="meta">
        <span>{item.title || new URL(item.url).hostname}</span>
        <time>{new Date(item.created_at).toLocaleDateString()}</time>
      </div>
    </li>
  );
}
