# teams.py — Divya's own team (v30+v31, Hark's "teams" method).
#
# Hark (2026-11-11): "Teams ante manushulu kaadu — oka pedda pani ni chinna
# parts ga chesi, prathi part ki separate AI helper ni oka clear task tho
# parallel ga pampistha. Fixed number ledu, pani batti create chestha."
# (Teams are not humans — split one big task into small parts, send each part
# to a separate AI helper with a clear task, in parallel. No fixed number —
# create them based on the work.)
#
# This module IS that pattern, shaped like CrewAI (Agent / Task / Crew) but
# running on Divya's Groq free tier via the existing groq_chat() — no heavy
# framework, no extra keys, no extra deps, no extra setup time per video.
#
# Frameworks evaluated (PyPI, 2026-11-11) — all do the same split + parallel
# + merge this module does in ~150 lines:
#   CrewAI v1.15.39 ......... 59 direct deps (needs LiteLLM for Groq)
#   OpenAI Agents SDK v0.24 . 56 direct deps (built for OpenAI, not Groq)
#   LangGraph v1.2.20 ........ pulls langchain-core + checkpoint + prebuilt
#   AutoGen (pyautogen) ...... pulls the whole agentchat ecosystem
# Installing any of them would add minutes to every runner setup and a new
# failure mode, for zero extra capability. The pattern is what matters, and
# it lives here. If a framework ever becomes necessary, this module's
# Agent/Task/Crew shape maps 1:1 onto CrewAI's, so the swap is mechanical.

import concurrent.futures as cf


class Agent:
    """A role-based helper: one clear job, one goal, one backstory."""

    def __init__(self, role, goal, backstory=""):
        self.role = role
        self.goal = goal
        self.backstory = backstory


class Task:
    """One clear task for one agent, with a defined expected output."""

    def __init__(self, description, expected_output, agent):
        self.description = description
        self.expected_output = expected_output
        self.agent = agent


class Crew:
    """Runs tasks in parallel and merges the results.

    chat() is the sync Groq call (runner.groq_chat). Tasks run on threads
    (max_workers=4) so the LLM calls overlap. A failed task returns "" —
    the caller falls back to the library/default — so one bad agent never
    kills the video. Groq free-tier rate limits: if the platform 429s,
    groq_chat's own key/model rotation handles it; the crew does not retry
    a failed task (the fallback covers it).
    """

    def __init__(self, agents, tasks, chat, max_workers=4):
        self.agents = agents
        self.tasks = tasks
        self.chat = chat
        self.max_workers = max_workers

    def _run_one(self, task):
        sys = (f"You are {task.agent.role}. Goal: {task.agent.goal}. "
               f"{task.agent.backstory}\n"
               f"Expected output: {task.expected_output}\n"
               f"Return only the requested output, nothing else.")
        return self.chat([{"role": "system", "content": sys},
                          {"role": "user", "content": task.description}])

    def kickoff(self):
        """Run every task in parallel. Returns {role: output}."""
        out = {}
        with cf.ThreadPoolExecutor(max_workers=self.max_workers) as ex:
            futs = {ex.submit(self._run_one, t): t for t in self.tasks}
            for fut in cf.as_completed(futs):
                t = futs[fut]
                try:
                    out[t.agent.role] = fut.result()
                except Exception as e:
                    out[t.agent.role] = ""
                    print(f"team: {t.agent.role} failed: {str(e)[:200]}")
        return out


# ---- Divya's standing team (roles Hark uses, per video) ----------------
# The orchestrator (doc.make_video) creates the crew per video: the same
# roles every time, but the TASKS differ (topic, scenes, look). That is
# Hark's "pani batti create chestha" — the team is built from the work.

SCRIPT_WRITER = Agent(
    "Script Writer",
    "Write the video's script: hook, scenes, voice lines.",
    "You write short, visual, fact-checked explainer scripts. One sentence = "
    "one scene (2-4s). Hook in the first 2s. No filler.")

VISUAL_ARTIST = Agent(
    "Visual Artist",
    "Draw each scene's visual in code (PIL), shaped like the topic's objects.",
    "You draw visuals pixel-by-pixel in Python (PIL ImageDraw): maps, "
    "documents, packets, charts, diagrams — whatever the sentence needs. "
    "Never a generic shape when a specific object fits.")

EFFECTS_ARTIST = Agent(
    "Effects Artist",
    "Write the video's custom motion code (transitions + emphasis).",
    "You write new tr_* and fx_* functions per video from the effects and "
    "transitions libraries' primitives. One effect at a time, on the hit word.")

QC_REVIEWER = Agent(
    "QC Reviewer",
    "Score every scene 1-5 and catch mistakes before the render.",
    "You check: does the visual fit the sentence? Is anything cut at the "
    "edges? Is the text readable? Is this scene different from the last "
    "video? Below 4, say exactly what is wrong.")
