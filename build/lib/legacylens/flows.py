"""Reconstruct online (CICS) and batch (JCL) transaction flows as edge lists."""

from __future__ import annotations

from legacylens.models import CobolProgram, Flow, FlowEdge, Job

_FILE_VERBS = {
    "READ": "reads-file",
    "READNEXT": "reads-file",
    "STARTBR": "browses-file",
    "WRITE": "writes-file",
    "REWRITE": "updates-file",
    "DELETE": "deletes-from-file",
}


def online_flows(programs: list[CobolProgram]) -> list[Flow]:
    flows: list[Flow] = []
    for program in programs:
        if program.program_type != "cics-online":
            continue
        edges: list[FlowEdge] = []
        transids = {
            c.options["TRANSID"]
            for c in program.cics_commands
            if c.command in {"RETURN", "START"} and c.options.get("TRANSID")
        }
        entry = f"TRAN:{sorted(transids)[0]}" if transids else f"PGM:{program.program_id}"
        for transid in sorted(transids):
            edges.append(FlowEdge(source=f"TRAN:{transid}", target=f"PGM:{program.program_id}", relation="starts"))
        for command in program.cics_commands:
            source = f"PGM:{program.program_id}"
            opts = command.options
            if command.command in {"SEND MAP", "RECEIVE MAP"}:
                target = f"MAP:{opts.get('MAPSET', '?')}.{opts.get('MAP', '?')}"
                relation = "sends-map" if command.command == "SEND MAP" else "receives-map"
            elif command.command in _FILE_VERBS and ("FILE" in opts or "DATASET" in opts):
                target = f"FILE:{opts.get('FILE') or opts.get('DATASET')}"
                relation = _FILE_VERBS[command.command]
            elif command.command in {"LINK", "XCTL"} and "PROGRAM" in opts:
                target = f"PGM:{opts['PROGRAM']}"
                relation = "links-to" if command.command == "LINK" else "transfers-to"
            else:
                continue
            edge = FlowEdge(source=source, target=target, relation=relation)
            if edge not in edges:
                edges.append(edge)
        for called in program.static_calls:
            edges.append(FlowEdge(source=f"PGM:{program.program_id}", target=f"PGM:{called}", relation="calls"))
        flows.append(Flow(name=f"{program.program_id} online flow", kind="online", entry=entry, edges=edges))
    return flows


def batch_flows(jobs: list[Job], programs: list[CobolProgram]) -> list[Flow]:
    by_id = {p.program_id: p for p in programs}
    flows: list[Flow] = []
    for job in jobs:
        edges: list[FlowEdge] = []
        for step in job.steps:
            step_node = f"STEP:{job.job_name}.{step.step_name}"
            edges.append(FlowEdge(source=f"JOB:{job.job_name}", target=step_node, relation="runs-step"))
            if not step.program:
                continue
            pgm_node = f"PGM:{step.program}"
            edges.append(FlowEdge(source=step_node, target=pgm_node, relation="executes"))
            program = by_id.get(step.program)
            ddnames = {f.ddname for f in program.files} if program else None
            for dd in step.dd_statements:
                if not dd.dsn or dd.ddname == "STEPLIB":
                    continue
                if ddnames is not None and dd.ddname not in ddnames:
                    continue
                disp = (dd.disp or "SHR").strip("()").split(",")[0].upper()
                relation = "writes-dataset" if disp in {"NEW", "MOD"} else "reads-dataset"
                edges.append(FlowEdge(source=pgm_node, target=f"DSN:{dd.dsn}", relation=relation))
            if program:
                for called in program.static_calls:
                    edges.append(FlowEdge(source=pgm_node, target=f"PGM:{called}", relation="calls"))
        flows.append(Flow(name=f"{job.job_name} batch flow", kind="batch", entry=f"JOB:{job.job_name}", edges=edges))
    return flows


def to_mermaid(flow: Flow) -> str:
    """Render a flow as a Mermaid flowchart (renders natively on GitHub)."""
    ids: dict[str, str] = {}

    def node(name: str) -> str:
        if name not in ids:
            ids[name] = f"n{len(ids)}"
        return ids[name]

    lines = ["flowchart LR"]
    body = []
    for edge in flow.edges:
        body.append(f"    {node(edge.source)} -->|{edge.relation}| {node(edge.target)}")
    for name, node_id in ids.items():
        kind, _, label = name.partition(":")
        shape = {"FILE": ("[(", ")]"), "DSN": ("[(", ")]"), "MAP": ("[/", "/]"), "TRAN": ("((", "))")}.get(
            kind, ("[", "]")
        )
        lines.append(f'    {node_id}{shape[0]}"{kind} {label}"{shape[1]}')
    return "\n".join(lines + body)
