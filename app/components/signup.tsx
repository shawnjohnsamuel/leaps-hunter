"use client";

import { useState } from "react";

export function SignupForm() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<"idle" | "busy" | "done" | "error">("idle");
  const [message, setMessage] = useState("");

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setState("busy");
    try {
      const res = await fetch("/api/subscribe", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body.error ?? "Something went wrong");
      setState("done");
      setMessage("Check your inbox to confirm your subscription.");
    } catch (err) {
      setState("error");
      setMessage(err instanceof Error ? err.message : "Something went wrong");
    }
  }

  if (state === "done") {
    return <p className="text-emerald-400">✓ {message}</p>;
  }

  return (
    <form onSubmit={submit} className="flex w-full max-w-md flex-col gap-3 sm:flex-row">
      <input
        type="email"
        required
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="you@example.com"
        className="flex-1 rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-3 text-zinc-100 placeholder-zinc-500 outline-none focus:border-emerald-500"
      />
      <button
        type="submit"
        disabled={state === "busy"}
        className="rounded-lg bg-emerald-500 px-6 py-3 font-semibold text-zinc-950 transition hover:bg-emerald-400 disabled:opacity-50"
      >
        {state === "busy" ? "…" : "Take the LEAP"}
      </button>
      {state === "error" && <p className="text-sm text-red-400 sm:self-center">{message}</p>}
    </form>
  );
}
