"""discuss: any number of team members talk in turn until they all agree, then the lead writes
the outcome to ROADMAP.md (updating it, never discarding what has shipped)."""
from __future__ import annotations

from pathlib import Path

from .. import agent, context, files, github, ui
from ..config import Team

PERSPECTIVES = {
    "lead": "Product lead: what users need, what makes the product worth using, realistic scope.",
    "builder": "Engineer: effort, technical risk, code quality and a sensible build order.",
    "devops": "DevOps: release cadence, CI, maintainability, and what the developer community asks for.",
    "marketing": "Marketing: how the product is positioned and what story each milestone lets us tell.",
    "factcheck": "Quality: what can be verified, tested and claimed honestly.",
}

FINAL = """The discussion is over. Write the agreed roadmap as ROADMAP.md:
<file path="ROADMAP.md">
...
</file>
Milestones in priority order, each with its features and reason. If anything was left unresolved,
add an "Open questions" section listing each position. If ROADMAP.md already exists, update it
rather than starting over: keep what has shipped (marked as shipped, with its version), keep the
Deferred list current, and add the new milestones after it."""


def feedback_digest(team: Team) -> str:
    """The devops member's latest digest of what developers ask for (.team/FEEDBACK.md), so the
    roadmap answers it. It summarises issues and PRs written by outsiders, so it arrives marked."""
    path = team.root / files.LOG_DIR / "FEEDBACK.md"
    if not path.exists():
        return "(No digest yet: a devops shift writes one.)"
    text = path.read_text(encoding="utf-8").strip()[:12_000]
    return github.untrusted(text) if text else "(The digest is empty.)"


def adopt_vision(team: Team, source: Path) -> str:
    """The text of a vision file given on the command line. When the project has no VISION.md yet,
    it's saved there, so every later workflow (build, reviews, market) works towards it too."""
    source = source.expanduser()
    if not source.is_file():
        raise SystemExit(f"--vision: {source} isn't a file")
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        raise SystemExit(f"--vision: {source} is empty")
    target = team.root / context.VISION
    if source.resolve() == target.resolve():
        return text
    if target.exists():
        ui.say(f"Using {source} for this discussion; the project's {context.VISION} is left as it is.")
    else:
        target.write_text(text + "\n", encoding="utf-8")
        ui.action(f"saved it as {context.VISION}: every workflow now reads it (commit it with the roadmap)")
    return text


NO_VISION = ("(No VISION.md yet: work from the README and the project files, and propose a one-paragraph "
             "vision in your first draft.)")


def run(team: Team, topic: str = "next milestones", members: list[str] | None = None, turns: int = 12,
        vision: str = "") -> bool:
    """vision: the owner's description of the product; default, the project's VISION.md."""
    vision = vision.strip() or context.vision(team)
    lead_cfg = team.by_role("lead")
    cfgs = [team.get(m) for m in members] if members else [lead_cfg, team.by_role("builder")]
    if lead_cfg not in cfgs:
        cfgs.insert(0, lead_cfg)
    if len(cfgs) < 2:
        raise SystemExit("A discussion needs at least two members.")
    project_files = context.for_topic(team, query=topic)
    people = [agent.make(team, c, "discuss", topic=topic, files=project_files, feedback=feedback_digest(team),
                         vision=vision or NO_VISION,
                         perspective=c.description or PERSPECTIVES.get(c.role, f"Your role: {c.role}."))
              for c in cfgs]
    log = files.Log(team.root, "discuss", f"Discussion: {topic}")
    names = ", ".join(p.name for p in people)
    ui.heading(f"Discussion: {topic} ({names}; up to {turns} messages)")

    # Each member hears everything said since its own last turn.
    pending = {p.name: [] for p in people}
    opener = (f"Let's plan the {topic} for this project. Participants: {names}. "
              f"You open: give your first proposals and what you need from the others.")
    statuses: dict[str, str] = {}
    agreed = False
    for i in range(turns):
        speaker = people[i % len(people)]
        heard = "\n\n".join(pending[speaker.name])
        pending[speaker.name] = []
        msg = opener if i == 0 else f"{heard}\n\n(Reply as yourself, {speaker.name}.)"
        reply = speaker.turn(msg)
        log.record(speaker.name, reply)
        statuses[speaker.name] = files.last_marker(files.STATUS_RE, reply) or "CONTINUE"
        for other in people:
            if other is not speaker:
                pending[other.name].append(f"{speaker.name} says:\n\n{reply}")
        if len(statuses) == len(people) and all(s == "AGREE" for s in statuses.values()):
            agreed = True
            ui.heading(f"Everyone agrees after {i + 1} messages.")
            break
        if statuses[speaker.name] == "CONTINUE":
            # Agreement must be unanimous on the latest draft, so any objection resets the others.
            statuses = {speaker.name: "CONTINUE"}
    if not agreed:
        ui.heading(f"No full agreement after {turns} messages; the lead records open questions.")

    lead = people[0]
    catch_up = "\n\n".join(pending[lead.name])
    final = lead.turn(f"{catch_up}\n\n{FINAL}" if catch_up else FINAL)
    written = files.write_files(team.root, final, allowed=("ROADMAP.md",))
    log.record("Final roadmap", final, written)
    ui.say(f"Saved: {', '.join(written) or 'nothing (no ROADMAP.md block)'}. Log: {log.path}")
    return agreed
