// Stripe paywall: plan buttons ask the backend for a Checkout Session (test mode) and redirect to it.
const API = "http://127.0.0.1:8766";
const msg = document.getElementById("billingMsg");
function say(text) {
  msg.textContent = text;
  msg.classList.remove("on");
  requestAnimationFrame(() => requestAnimationFrame(() => msg.classList.add("on")));
}
msg.setAttribute("data-write-like", "");

document.querySelectorAll("[data-plan]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const label = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Opening Stripe…";
    try {
      const r = await fetch(`${API}/billing/checkout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan: btn.dataset.plan }),
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok && data.url) { location.href = data.url; return; }
      say(r.status === 503 ? "Stripe not set up yet → add a test key in backend/.env" : `Checkout failed (${r.status})`);
    } catch {
      say("Backend offline → run hcs-backend serve");
    }
    btn.disabled = false;
    btn.textContent = label;
  });
});

const q = new URLSearchParams(location.search);
if (q.get("checkout") === "success") say(`Payment received ✓ — welcome to ${q.get("plan") === "fixpack" ? "the Fix pack" : "Pro"} (test mode)`);
if (q.get("checkout") === "cancel") say("Checkout cancelled — no charge.");
