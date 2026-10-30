"""Build the public website (site/, deployed by Vercel) from the pages below.

    uv run python scripts/build_site.py

The site is the landing page plus what the App Store, Google Play and the
DMCA require: privacy policy, terms, copyright (DMCA) policy, support, and
account deletion. Fill the OWNER values before the first deploy; every page
says "[to fill]" until then. The policies are drafts to be reviewed by a
lawyer before launch.
"""

from __future__ import annotations

from datetime import date
from html import escape
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "site"
UPDATED = date(2026, 10, 30).strftime("%-d %B %Y")

# Fill these before the first deploy (backend/SETUP.md, step 6).
OWNER = {
    "name": "[to fill: your legal name or company]",
    "email": "[to fill: support email]",
    "address": "[to fill: postal address for legal notices]",
    "country": "[to fill: governing country]",
}

NAV = [("Privacy", "/privacy"), ("Terms", "/terms"), ("Support", "/support")]
FOOT = [("Privacy", "/privacy"), ("Terms", "/terms"), ("Copyright (DMCA)", "/dmca"),
        ("Delete account", "/delete-account"), ("Support", "/support")]


def page(slug: str, title: str, body: str, description: str) -> None:
    nav = "".join(f'<a href="{h}">{escape(t)}</a>' for t, h in NAV)
    foot = "".join(f'<a href="{h}">{escape(t)}</a>' for t, h in FOOT)
    html = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<meta name="description" content="{escape(description)}">
<link rel="icon" href="/icon.svg" type="image/svg+xml">
<link rel="stylesheet" href="/site.css">
</head>
<body>
<header><a class="brand" href="/"><img src="/icon.svg" alt="">Amin</a><nav>{nav}</nav></header>
<main>
{body.format(**OWNER, updated=UPDATED)}
</main>
<footer><span>© {date.today().year} {escape(OWNER["name"])}</span>{foot}</footer>
</body>
</html>
"""
    (OUT / f"{slug}.html").write_text(html, encoding="utf-8")


INDEX = """
<h1>The assistant that keeps your life on your own devices.</h1>
<p class="lead">Amin answers from your own documents and shows you the passage it used.
It runs on your iPhone, iPad and Mac, in English, Arabic and Malayalam. What you ask
and what you share never leaves your device.</p>
<p><a class="button" href="/support">Get Amin</a></p>
<div class="cards">
  <div class="card"><b>Private by design</b><p>The model runs on your device. No one, including us, can read your questions or documents.</p></div>
  <div class="card"><b>Answers you can check</b><p>Every answer from your documents cites the exact passage. When it doesn't know, it says so.</p></div>
  <div class="card"><b>Three languages</b><p>English, Arabic and Malayalam, spoken or typed. Say “Hey Amin”.</p></div>
  <div class="card"><b>Teach it, not train it</b><p>Tell Amin facts to remember. You can see, edit and delete every one.</p></div>
</div>
"""

PRIVACY = """
<h1>Privacy policy</h1>
<p class="updated">Last updated {updated}</p>
<p class="note">The short version: your questions, documents, memories, conversations and voice
stay on your own devices. Our servers hold only your account and your subscription.</p>

<h2>Who we are</h2>
<p>Amin is provided by {name} (“we”), {address}. Contact: {email}.</p>

<h2>What stays on your device</h2>
<p>Everything you ask, every document you add, the facts you teach Amin, your conversation
history and anything you say to it. Amin's language model and speech recognition run on your
device. If you connect Amin to your own Amin computer at home, that data goes to that computer
over your home network, which you control. We never receive it.</p>

<h2>What we hold</h2>
<ul>
  <li><b>Account:</b> your email address, a display name if you give one, your interface language,
  and when the account was created. Passwords are stored by our authentication provider as salted hashes.</li>
  <li><b>Subscription:</b> your plan, the product bought, the store it was bought through, and when it renews or ends.
  Payment details are handled by Apple or Google; we never see them.</li>
</ul>
<p>We use this only to sign you in, give you the features of your plan, and contact you about your
account. We do not sell it, use it for advertising, or use it to train models.</p>

<h2>Service providers</h2>
<ul>
  <li><b>Supabase</b>: hosts the account database and sign-in.</li>
  <li><b>RevenueCat</b>: manages subscriptions with Apple and Google, linked to your account by an anonymous id.</li>
  <li><b>Apple App Store, Google Play</b>: process payments under their own policies.</li>
  <li><b>Hugging Face</b>: hosts the model file your device downloads once. Like any download, it sees your IP address.</li>
  <li><b>Vercel</b>: hosts this website.</li>
</ul>

<h2>Your rights</h2>
<p>You can see and correct your account details in the app, and delete your account at any time
in Settings › Account › Delete account or at <a href="/delete-account">amin's deletion page</a>.
Deleting it removes your account and subscription record from our servers. Data on your devices
is removed when you delete the app. Depending on where you live (for example the UK and EU GDPR,
or California's CCPA) you may also ask us for a copy of your data or to restrict its use: write to {email}.</p>

<h2>Retention</h2>
<p>Account and subscription records are kept while your account exists and deleted when you delete it,
except where the law requires us to keep billing records.</p>

<h2>Children</h2>
<p>Amin is not directed at children under 13. Students under 18 should use it with a parent's or guardian's agreement.</p>

<h2>Changes</h2>
<p>If this policy changes in a way that matters, we will say so in the app before it takes effect.</p>
"""

TERMS = """
<h1>Terms of use</h1>
<p class="updated">Last updated {updated}</p>

<h2>The service</h2>
<p>Amin is an assistant app provided by {name}. These terms apply when you create an account or use the app.</p>

<h2>Your account</h2>
<p>Give a real email address and keep your password to yourself. You are responsible for what happens under your account.
You must be at least 13, or the minimum age for digital consent where you live.</p>

<h2>Subscriptions</h2>
<p>Amin has a free plan and a paid Pro plan. Pro is billed through the App Store or Google Play, renews automatically
until cancelled, and is cancelled in your store account settings at least 24 hours before renewal. Refunds are handled by
Apple or Google under their policies.</p>

<h2>Answers are help, not advice</h2>
<p>Amin can be wrong. It says when an answer comes from your documents and when it is general knowledge, but you must check
anything important. It is not medical, legal, financial or other professional advice, and it is not an emergency service.</p>

<h2>Your content</h2>
<p>Your documents and questions stay yours and stay on your devices. Only add material you have the right to use.
Knowledge packs in the app are openly licensed works, credited to their authors under their licences.</p>

<h2>Acceptable use</h2>
<p>Don't use Amin to break the law, to infringe others' rights, or to try to break, copy or resell the service.</p>

<h2>Liability</h2>
<p>The app is provided “as is”. To the extent the law allows, we are not liable for indirect or consequential loss, and our
total liability is limited to what you paid us in the 12 months before the claim. Nothing here limits rights you have as a consumer.</p>

<h2>Ending</h2>
<p>You can delete your account at any time. We may suspend accounts that break these terms.</p>

<h2>Law</h2>
<p>These terms are governed by the law of {country}. Questions: {email}.</p>
"""

DMCA = """
<h1>Copyright policy (DMCA)</h1>
<p class="updated">Last updated {updated}</p>
<p>We respect copyright and respond to notices under the US Digital Millennium Copyright Act (17 U.S.C. § 512) and
similar laws elsewhere.</p>

<h2>What we host</h2>
<p>Documents you add to Amin stay on your own devices; we do not host them and cannot see them. What we distribute is the
app, its model, and its knowledge packs, which are openly licensed works (for example OpenStax textbooks under CC BY 4.0 and
the Python documentation under the PSF License), credited to their authors.</p>

<h2>Sending a notice</h2>
<p>If you believe something we distribute infringes your copyright, send our designated agent a notice that includes:</p>
<ol>
  <li>your physical or electronic signature;</li>
  <li>the copyrighted work you say is infringed;</li>
  <li>the material you say infringes it, and where in Amin it appears;</li>
  <li>your name, address, telephone number and email;</li>
  <li>a statement that you believe in good faith the use is not authorised by the owner, its agent or the law;</li>
  <li>a statement, under penalty of perjury, that the notice is accurate and that you are the owner or authorised to act for them.</li>
</ol>

<h2>Designated agent</h2>
<p>{name}<br>{address}<br>{email}</p>

<h2>Counter-notices and repeat infringers</h2>
<p>If material you provided was removed and you believe that was a mistake, you may send a counter-notice with the details
required by 17 U.S.C. § 512(g)(3). We end the accounts of repeat infringers where appropriate.</p>
"""

SUPPORT = """
<h1>Support</h1>
<p class="lead">Questions, problems or ideas: write to {email}. We read everything.</p>
<h2>Common questions</h2>
<p><b>Does Amin send my documents anywhere?</b> No. They stay on your device, or on your own Amin computer if you use one.</p>
<p><b>Which devices can run the model?</b> iPhones with 8 GB of memory (iPhone 15 Pro and later), iPads and Macs with Apple silicon.</p>
<p><b>How do I cancel Pro?</b> In your Apple ID or Google Play subscriptions. Your plan stays active until the end of the period.</p>
<p><b>How do I delete my account?</b> In the app, Settings › Account › Delete account, or see <a href="/delete-account">account deletion</a>.</p>
"""

DELETE = """
<h1>Delete your account</h1>
<p>In the Amin app, open <b>Settings › Account › Delete account</b>. Your account and subscription record are deleted from our
servers at once. Your documents and conversations are on your device, so deleting the app removes them.</p>
<p>If you can no longer open the app, email {email} from the address on your account and we will delete it within 30 days.</p>
<p class="note">Deleting your account does not cancel an App Store or Google Play subscription. Cancel it in your store account settings first.</p>
"""

CONFIRMED = """
<h1>Your email is confirmed.</h1>
<p class="lead">Go back to the Amin app and sign in.</p>
"""


def main() -> None:
    OUT.mkdir(exist_ok=True)
    page("index", "Amin, the private assistant", INDEX, "A private AI assistant that answers from your own documents, on your own devices.")
    page("privacy", "Privacy policy · Amin", PRIVACY, "What Amin keeps on your device and the little it keeps in the cloud.")
    page("terms", "Terms of use · Amin", TERMS, "The terms for using Amin.")
    page("dmca", "Copyright policy · Amin", DMCA, "How to send Amin a copyright (DMCA) notice.")
    page("support", "Support · Amin", SUPPORT, "Help with Amin.")
    page("delete-account", "Delete your account · Amin", DELETE, "How to delete your Amin account.")
    (OUT / "auth").mkdir(exist_ok=True)
    page("auth/confirmed", "Email confirmed · Amin", CONFIRMED, "Your Amin email address is confirmed.")
    print(f"built {len(list(OUT.rglob('*.html')))} pages in {OUT}")


if __name__ == "__main__":
    main()
