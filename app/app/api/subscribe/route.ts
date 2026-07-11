import { NextResponse } from "next/server";

// Subscribers live in a Resend Audience (no database — plan Part 7.3). Resend manages
// unsubscribe links and suppression. Requires RESEND_API_KEY + RESEND_AUDIENCE_ID.
export async function POST(req: Request) {
  const { email } = await req.json().catch(() => ({ email: null }));
  if (typeof email !== "string" || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    return NextResponse.json({ error: "Enter a valid email address." }, { status: 400 });
  }

  const key = process.env.RESEND_API_KEY;
  const audience = process.env.RESEND_AUDIENCE_ID;
  if (!key || !audience) {
    return NextResponse.json(
      { error: "Signups aren't open quite yet — check back soon." },
      { status: 503 },
    );
  }

  const res = await fetch(`https://api.resend.com/audiences/${audience}/contacts`, {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({ email, unsubscribed: false }),
  });

  if (!res.ok) {
    const detail = await res.text();
    console.error("resend subscribe failed:", res.status, detail);
    return NextResponse.json({ error: "Could not subscribe right now — try again later." }, { status: 502 });
  }

  return NextResponse.json({ ok: true });
}
