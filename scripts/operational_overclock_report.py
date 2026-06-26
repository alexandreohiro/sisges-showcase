from __future__ import annotations

import argparse
import json
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean
from time import perf_counter

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

import infra.persistence.models  # noqa: F401
from apps.web.app import app
from infra.persistence.db import Base, get_db
from infra.persistence.models import MilitarModel, PermissionModel, RoleModel, TarefaModel, UserModel
from infra.security.passwords import hash_password


DEFAULT_ENDPOINTS = [
    "/tarefas?limit=180",
    "/tarefas/resumo",
    "/gestao-pessoal?view_scope=efetivo_completo&limit=180",
    "/gestao-pessoal/filtros",
    "/gestao-pessoal/efetivo-om?om=DIV%20PES&limit=700",
]
REPO_ROOT = Path(__file__).resolve().parents[1]
PROFILE_ENDPOINT_FILES = {
    "critical": REPO_ROOT / "ops" / "overclock" / "critical_endpoints.txt",
}

OVERLCLOCK_PERMISSIONS = [
    "mod.gestao_pessoal.view",
    "mod.gestao_pessoal.create",
    "mod.gestao_pessoal.edit",
    "mod.gestao_pessoal.delete",
    "mod.tarefas.view",
    "mod.tarefas.create",
    "mod.tarefas.edit",
    "mod.tarefas.assign",
    "mod.tarefas.close",
]


@dataclass(slots=True)
class EndpointTiming:
    endpoint: str
    status_codes: list[int]
    elapsed_ms: list[float]
    max_seconds: float
    response_items: int | None = None

    @property
    def ok(self) -> bool:
        return all(status == 200 for status in self.status_codes) and max(self.elapsed_ms, default=0.0) < (
            self.max_seconds * 1000
        )

    def to_dict(self) -> dict:
        return {
            "endpoint": self.endpoint,
            "ok": self.ok,
            "status_codes": self.status_codes,
            "response_items": self.response_items,
            "elapsed_ms": endpoint_timing_summary(self.elapsed_ms),
            "threshold_ms": round(self.max_seconds * 1000, 3),
        }


def percentile(values: list[float], percentile_value: int) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    index = round((percentile_value / 100) * (len(ordered) - 1))
    return ordered[index]


def endpoint_timing_summary(values: list[float]) -> dict[str, float]:
    return {
        "min": round(min(values), 3),
        "avg": round(mean(values), 3),
        "p50": round(percentile(values, 50), 3),
        "p90": round(percentile(values, 90), 3),
        "p95": round(percentile(values, 95), 3),
        "p99": round(percentile(values, 99), 3),
        "max": round(max(values), 3),
    }


def compare_report_to_baseline(
    *,
    current_report: dict,
    baseline_report: dict,
    metric: str = "p95",
    tolerance_percent: float = 35.0,
) -> dict:
    current_by_endpoint = {endpoint["endpoint"]: endpoint for endpoint in current_report.get("endpoints", [])}
    baseline_by_endpoint = {endpoint["endpoint"]: endpoint for endpoint in baseline_report.get("endpoints", [])}
    comparisons: list[dict] = []

    for endpoint, current_endpoint in current_by_endpoint.items():
        current_value = float(current_endpoint.get("elapsed_ms", {}).get(metric, 0.0))
        baseline_endpoint = baseline_by_endpoint.get(endpoint)
        if baseline_endpoint is None:
            comparisons.append(
                {
                    "endpoint": endpoint,
                    "status": "MISSING_BASELINE",
                    "ok": True,
                    "metric": metric,
                    "current_ms": round(current_value, 3),
                    "baseline_ms": None,
                    "allowed_ms": None,
                    "delta_percent": None,
                }
            )
            continue

        baseline_value = float(baseline_endpoint.get("elapsed_ms", {}).get(metric, 0.0))
        allowed_value = baseline_value * (1 + (tolerance_percent / 100))
        ok = current_value <= allowed_value
        delta_percent = None
        if baseline_value > 0:
            delta_percent = round(((current_value - baseline_value) / baseline_value) * 100, 3)
        comparisons.append(
            {
                "endpoint": endpoint,
                "status": "OK" if ok else "REGRESSION",
                "ok": ok,
                "metric": metric,
                "current_ms": round(current_value, 3),
                "baseline_ms": round(baseline_value, 3),
                "allowed_ms": round(allowed_value, 3),
                "delta_percent": delta_percent,
            }
        )

    for endpoint in sorted(set(baseline_by_endpoint) - set(current_by_endpoint)):
        baseline_value = float(baseline_by_endpoint[endpoint].get("elapsed_ms", {}).get(metric, 0.0))
        comparisons.append(
            {
                "endpoint": endpoint,
                "status": "MISSING_CURRENT_ENDPOINT",
                "ok": True,
                "metric": metric,
                "current_ms": None,
                "baseline_ms": round(baseline_value, 3),
                "allowed_ms": None,
                "delta_percent": None,
            }
        )

    return {
        "status": "OK" if all(comparison["ok"] for comparison in comparisons) else "FAIL",
        "metric": metric,
        "tolerance_percent": tolerance_percent,
        "baseline_profile_label": baseline_report.get("profile_label"),
        "comparisons": comparisons,
    }


def seed_auth_context(db: Session) -> None:
    permissions = [PermissionModel(id=key, key=key) for key in OVERLCLOCK_PERMISSIONS]
    role = RoleModel(id="overclock", name="overclock", permissions=permissions)
    user = UserModel(
        id="overclock-user",
        username="operador",
        display_name="Operador Overclock",
        email="overclock@sisges.local",
        password_hash=hash_password("senha-forte-123"),
        is_active=True,
        roles=[role],
        secao="SECRETARIA",
        divisao="DIV PES",
    )
    db.add_all([*permissions, role, user])
    db.commit()


def seed_operational_volume(db: Session, *, tarefas_total: int, efetivo_total: int) -> None:
    task_militares = [
        MilitarModel(
            nome_completo=f"MILITAR OVERCLOCK {index:03d}",
            nome_guerra=f"OVR{index:03d}",
            posto_graduacao="3 Sgt",
            identidade=f"OVR{index:07d}",
            secao="SECRETARIA",
            om="DIV PES",
            local_om="DIV PES",
            ativo=True,
        )
        for index in range(tarefas_total)
    ]
    db.add_all(task_militares)
    db.flush()

    tasks = [
        TarefaModel(
            codigo=f"OVR-{index:06d}",
            titulo=f"Tarefa operacional {index:03d}",
            tipo="cadastro",
            prioridade="media" if index % 5 else "critica",
            status="nova",
            origem_modulo="gestao_pessoal",
            secao_responsavel="SECRETARIA",
            divisao_responsavel="DIV PES",
            militar_id=task_militares[index].id,
            criado_por_user_id="overclock-user",
        )
        for index in range(tarefas_total)
    ]
    db.add_all(tasks)

    ranks = ["Cel", "Ten Cel", "Maj", "Cap", "STen", "1º Sgt", "2º Sgt", "3º Sgt", "Cb", "Sd", "Rcr"]
    secoes = ["SECRETARIA", "PROTOCOLO", "ARQUIVO", "FISCALIZACAO"]
    efetivo = []
    for index in range(efetivo_total):
        in_div_pes = index < int(efetivo_total * 0.8)
        efetivo.append(
            MilitarModel(
                nome_completo=f"EFETIVO OVERCLOCK {index:04d}",
                nome_guerra=f"EFV{index:04d}",
                posto_graduacao=ranks[index % len(ranks)],
                identidade=f"EFV{index:07d}",
                secao=secoes[index % len(secoes)],
                om="DIV PES" if in_div_pes else "OUTRA OM",
                local_om="DIV PES" if in_div_pes else "OUTRA OM",
                ativo=index % 29 != 0,
                status_servico="Reserva" if index % 37 == 0 else "Ativo",
            )
        )
    db.add_all(efetivo)
    db.commit()


def measure_endpoint(client: TestClient, endpoint: str, *, repeat: int, max_seconds: float) -> EndpointTiming:
    status_codes: list[int] = []
    elapsed_ms: list[float] = []
    response_items: int | None = None

    for _ in range(repeat):
        start = perf_counter()
        response = client.get(endpoint)
        elapsed_ms.append((perf_counter() - start) * 1000)
        status_codes.append(response.status_code)
        if response.status_code == 200:
            try:
                data = response.json()
            except ValueError:
                data = None
            if isinstance(data, list):
                response_items = len(data)
            elif isinstance(data, dict) and "total" in data:
                response_items = int(data["total"])

    return EndpointTiming(
        endpoint=endpoint,
        status_codes=status_codes,
        elapsed_ms=elapsed_ms,
        response_items=response_items,
        max_seconds=max_seconds,
    )


def generate_report(
    *,
    output_json: Path,
    output_txt: Path,
    endpoints: Iterable[str] = DEFAULT_ENDPOINTS,
    tarefas_total: int = 180,
    efetivo_total: int = 700,
    repeat: int = 3,
    max_seconds: float = 5.0,
    profile_label: str = "default",
    baseline_report: dict | None = None,
    baseline_metric: str = "p95",
    regression_tolerance_percent: float = 35.0,
) -> dict:
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_txt.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="sisges-overclock-") as temp_dir:
        db_path = Path(temp_dir) / "overclock.db"
        engine = create_engine(
            f"sqlite:///{db_path.as_posix()}",
            connect_args={"check_same_thread": False, "timeout": 15},
        )
        Base.metadata.create_all(bind=engine)
        session_factory = sessionmaker(bind=engine)
        db = session_factory()
        try:
            seed_auth_context(db)
            seed_operational_volume(db, tarefas_total=tarefas_total, efetivo_total=efetivo_total)
        finally:
            db.close()

        def override_get_db():
            session = session_factory()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        try:
            with TestClient(app) as client:
                login = client.post("/auth/login", json={"username": "operador", "password": "senha-forte-123"})
                login.raise_for_status()
                timings = [
                    measure_endpoint(client, endpoint, repeat=repeat, max_seconds=max_seconds)
                    for endpoint in endpoints
                ]
        finally:
            app.dependency_overrides.clear()
            engine.dispose()

    report = {
        "schema_version": "sisges-operational-overclock-v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "status": "OK" if all(timing.ok for timing in timings) else "FAIL",
        "seed": {
            "tarefas_total": tarefas_total,
            "efetivo_total": efetivo_total,
            "database": "temporary_sqlite",
        },
        "repeat": repeat,
        "max_seconds": max_seconds,
        "profile_label": profile_label,
        "endpoints": [timing.to_dict() for timing in timings],
    }
    if baseline_report is not None:
        baseline_comparison = compare_report_to_baseline(
            current_report=report,
            baseline_report=baseline_report,
            metric=baseline_metric,
            tolerance_percent=regression_tolerance_percent,
        )
        report["baseline_comparison"] = baseline_comparison
        if baseline_comparison["status"] != "OK":
            report["status"] = "FAIL"

    output_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    output_txt.write_text(render_text_report(report), encoding="utf-8")
    return report


def render_text_report(report: dict) -> str:
    lines = [
        "RELATORIO DE TIMING OPERACIONAL SISGES",
        f"Gerado em: {report['generated_at']}",
        f"Status: {report['status']}",
        "",
        "Carga sintetica:",
        f"- tarefas: {report['seed']['tarefas_total']}",
        f"- efetivo: {report['seed']['efetivo_total']}",
        f"- banco: {report['seed']['database']}",
        f"- repeticoes por endpoint: {report['repeat']}",
        f"- limite por requisicao: {report['max_seconds']}s",
        f"- perfil: {report.get('profile_label', 'default')}",
        "",
        "Endpoints:",
    ]
    for endpoint in report["endpoints"]:
        timing = endpoint["elapsed_ms"]
        lines.append(
            (
                "- {endpoint} | {status} | min={min}ms avg={avg}ms p50={p50}ms "
                "p90={p90}ms p95={p95}ms p99={p99}ms max={max}ms items={items}"
            ).format(
                endpoint=endpoint["endpoint"],
                status="OK" if endpoint["ok"] else "FAIL",
                min=timing["min"],
                avg=timing["avg"],
                p50=timing["p50"],
                p90=timing["p90"],
                p95=timing["p95"],
                p99=timing["p99"],
                max=timing["max"],
                items=endpoint["response_items"],
            )
        )
    baseline_comparison = report.get("baseline_comparison")
    if baseline_comparison:
        lines.extend(
            [
                "",
                "Comparacao com baseline:",
                f"- status: {baseline_comparison['status']}",
                f"- metrica: {baseline_comparison['metric']}",
                f"- tolerancia: {baseline_comparison['tolerance_percent']}%",
                f"- perfil baseline: {baseline_comparison.get('baseline_profile_label')}",
            ]
        )
        for comparison in baseline_comparison["comparisons"]:
            lines.append(
                (
                    "- {endpoint} | {status} | atual={current}ms baseline={baseline}ms "
                    "permitido={allowed}ms delta={delta}%"
                ).format(
                    endpoint=comparison["endpoint"],
                    status=comparison["status"],
                    current=comparison["current_ms"],
                    baseline=comparison["baseline_ms"],
                    allowed=comparison["allowed_ms"],
                    delta=comparison["delta_percent"],
                )
            )
    return "\n".join(lines) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera relatorio local de timing operacional do SISGES.")
    parser.add_argument("--output-json", type=Path, default=Path("data/output/operational_overclock_timings.json"))
    parser.add_argument("--output-txt", type=Path, default=Path("data/output/operational_overclock_timings.txt"))
    parser.add_argument("--tarefas", type=int, default=180)
    parser.add_argument("--efetivo", type=int, default=700)
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--max-seconds", type=float, default=5.0)
    parser.add_argument(
        "--profile",
        choices=sorted(PROFILE_ENDPOINT_FILES),
        default=None,
        help="Perfil versionado de endpoints criticos. Ignorado quando --endpoints-file e informado.",
    )
    parser.add_argument("--profile-label", default="default")
    parser.add_argument(
        "--baseline-json",
        type=Path,
        default=None,
        help="Relatorio JSON anterior usado como baseline para detectar regressao de timing.",
    )
    parser.add_argument(
        "--baseline-metric",
        default="p95",
        choices=["min", "avg", "p50", "p90", "p95", "p99", "max"],
        help="Metrica de elapsed_ms usada na comparacao com baseline.",
    )
    parser.add_argument(
        "--regression-tolerance-percent",
        type=float,
        default=35.0,
        help="Tolerancia percentual acima da baseline antes de marcar regressao.",
    )
    parser.add_argument(
        "--endpoints-file",
        type=Path,
        default=None,
        help="Arquivo texto opcional com um endpoint por linha. Linhas vazias e comentarios # sao ignorados.",
    )
    return parser.parse_args()


def read_endpoints_file(path: Path | None) -> list[str] | None:
    if path is None:
        return None
    endpoints = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line and not line.startswith("#"):
            endpoints.append(line)
    return endpoints


def read_endpoints_profile(profile: str | None) -> list[str] | None:
    if profile is None:
        return None
    try:
        profile_path = PROFILE_ENDPOINT_FILES[profile]
    except KeyError as exc:
        raise ValueError(f"Perfil de overclock desconhecido: {profile}") from exc
    return read_endpoints_file(profile_path)


def resolve_endpoints(*, endpoints_file: Path | None, profile: str | None) -> list[str]:
    if endpoints_file is not None:
        return read_endpoints_file(endpoints_file) or []
    return read_endpoints_profile(profile) or DEFAULT_ENDPOINTS


def read_baseline_report(path: Path | None) -> dict | None:
    if path is None:
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    args = parse_args()
    profile_label = args.profile_label
    if profile_label == "default" and args.profile:
        profile_label = args.profile
    report = generate_report(
        output_json=args.output_json,
        output_txt=args.output_txt,
        endpoints=resolve_endpoints(endpoints_file=args.endpoints_file, profile=args.profile),
        tarefas_total=args.tarefas,
        efetivo_total=args.efetivo,
        repeat=args.repeat,
        max_seconds=args.max_seconds,
        profile_label=profile_label,
        baseline_report=read_baseline_report(args.baseline_json),
        baseline_metric=args.baseline_metric,
        regression_tolerance_percent=args.regression_tolerance_percent,
    )
    print(render_text_report(report))
    if report["status"] != "OK":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
