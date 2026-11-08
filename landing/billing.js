// Public demo only. No checkout API, localhost request, redirect or payment assertion.
// Old shared checkout links remain understandable without treating query parameters as proof of payment.
const msg = document.getElementById("billingMsg");
if (msg && new URLSearchParams(location.search).has("checkout")) {
  msg.textContent = "This is the H Companion demo. Subscriptions and payments are not available on this site.";
  msg.classList.add("on");
}
