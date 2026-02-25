"""자율 개발 에이전트 메인 루프.

상위 Orchestrator가 Claude API(두뇌)와 Claude Agent SDK(손발)를 조합하여
프로젝트를 테스트 100% + 전체 완성 100%까지 자율 반복 개발한다.

핵심 규칙:
- 크리티컬 이슈만 즉시 사람에게 질문
- 빌드/테스트 실패는 에이전트가 스스로 해결
- 토큰 한도 도달 시 리셋될 때까지 대기 후 이어서 진행
- 비크리티컬 질문은 완성 후 모아서 전달
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

from src.orchestrator.planner import Planner
from src.orchestrator.issue_classifier import IssueClassifier, IssueLevel
from src.orchestrator.token_manager import TokenManager
from src.agents.executor import AgentExecutor
from src.agents.verifier import Verifier
from src.utils.state import ProjectState, PhaseType
from src.utils.logger import setup_logger

logger = setup_logger(__name__)

# 완성 판단 기준
COMPLETION_CRITERIA = {
    "test_pass_rate": 100.0,
    "lint_errors": 0,
    "type_errors": 0,
    "build_success": True,
    "all_features_implemented": True,
}

MAX_ITERATIONS = 500  # 안전장치: 무한 루프 방지


class AutonomousOrchestrator:
    """자율 개발 에이전트 Orchestrator.
    
    Claude API로 판단하고, Claude Agent SDK로 실행하는 상위 에이전트.
    """

    def __init__(self, project_path: str, spec: str):
        self.project_path = Path(project_path)
        self.state = ProjectState(spec=spec)
        self.planner = Planner()
        self.classifier = IssueClassifier()
        self.token_manager = TokenManager()
        self.executor = AgentExecutor(project_path)
        self.verifier = Verifier(project_path)

    async def run(self) -> None:
        """메인 자율 루프. 완성될 때까지 멈추지 않는다."""
        logger.info("=== 자율 개발 에이전트 시작 ===")
        logger.info(f"프로젝트 경로: {self.project_path}")

        # Phase 1: 프로젝트 초기 구성
        await self._phase_setup()

        # Phase 2~5: 무한 반복 (완성될 때까지)
        while not self._is_complete():
            self.state.iteration += 1

            if self.state.iteration > MAX_ITERATIONS:
                logger.warning(f"최대 반복 횟수({MAX_ITERATIONS}) 도달. 중간 보고 후 종료.")
                break

            logger.info(
                f"\n[Iteration {self.state.iteration}] "
                f"완성도: {self.state.completion_percent:.1f}% | "
                f"테스트: {self.state.test_pass_rate:.1f}% | "
                f"Phase: {self.state.phase}"
            )

            # 토큰 한도 체크 → 초과 시 리셋될 때까지 대기
            await self.token_manager.wait_if_needed()

            try:
                # 1) 다음 작업 결정 (Claude API)
                next_task = await self.planner.decide_next_task(self.state)

                # 2) 작업 실행 (Claude Agent SDK)
                result = await self.executor.execute(next_task)

                # 3) 결과 검증 (Claude Agent SDK)
                verification = await self.verifier.verify_all()

                # 4) 이슈 분류 (Claude API)
                issues = await self.classifier.classify(verification)

                # 5) 이슈 처리
                await self._handle_issues(issues)

                # 6) 상태 업데이트
                self._update_state(verification)

            except TokenLimitError:
                # 토큰 한도 초과 → 대기 후 이어서
                logger.warning("토큰 한도 초과. 리셋 대기 중...")
                await self.token_manager.wait_for_reset()
                continue

            except Exception as e:
                # 예상치 못한 에러도 스스로 해결 시도
                logger.error(f"예상치 못한 에러: {e}")
                await self._self_heal(str(e))

        # Phase 6: 문서화 (코드 완성 후)
        await self._phase_document()

        # Phase 7: 완성 보고
        await self._report_completion()

    async def _phase_document(self) -> None:
        """Phase 6: 문서화. 코드 완성 후 documenter 에이전트가 전체 문서를 생성한다."""
        self.state.phase = PhaseType.DOCUMENT
        logger.info("Phase 6: 문서화")

        doc_prompt = """
프로젝트 코드가 완성되었습니다. 전체 문서를 생성하세요.

.claude/agents/documenter.md 의 규칙을 따라 다음 문서를 생성하세요:

1. README.md — 프로젝트 개요, 설치, 설정, 실행까지 완전한 가이드
2. docs/api/ — 모든 API 엔드포인트 문서 (실제 코드에서 추출)
3. docs/architecture/overview.md — 시스템 아키텍처, 모듈 의존성
4. docs/architecture/data-model.md — 데이터베이스 스키마, 엔티티
5. docs/architecture/design-decisions.md — 주요 설계 결정과 이유
6. docs/setup/development.md — 개발 환경 설정
7. docs/setup/deployment.md — 배포 가이드
8. CHANGELOG.md — 현재 버전 변경사항

규칙:
- 추측하지 말 것. 실제 코드를 읽고 확인한 내용만 문서화
- API 문서는 실제 라우터/컨트롤러에서 추출
- 코드 예시는 실제 동작하는 것으로
"""
        await self.executor.execute(doc_prompt)

    async def _phase_setup(self) -> None:
        """Phase 1: 프로젝트 초기 구성."""
        self.state.phase = PhaseType.SETUP
        logger.info("Phase 1: 프로젝트 초기 구성")

        setup_prompt = f"""
프로젝트 스펙에 따라 초기 구성을 수행하세요.

[스펙]
{self.state.spec}

수행할 작업:
1. 디렉토리 구조 생성 (design-patterns 스킬 참조)
2. 패키지 매니저 초기화 (pyproject.toml 또는 package.json)
3. 기본 설정 파일 생성
4. 디자인 패턴에 맞는 베이스 코드 스캐폴딩
5. 테스트 프레임워크 설정
6. 린트/타입체크 설정

반드시 .claude/skills/ 의 모든 스킬을 읽고 따르세요.
"""
        await self.executor.execute(setup_prompt)
        self.state.phase = PhaseType.BUILD

    async def _handle_issues(self, issues: list) -> None:
        """이슈를 분류하여 처리한다."""
        for issue in issues:
            if issue["level"] == IssueLevel.CRITICAL:
                # 크리티컬: 즉시 사람에게 질문
                answer = await self._ask_human(issue)
                if answer:
                    await self.executor.execute(
                        f"사람의 답변에 따라 수정하세요:\n"
                        f"질문: {issue['description']}\n"
                        f"답변: {answer}"
                    )
            else:
                # 비크리티컬: 모아두기
                self.state.pending_questions.append(issue)

    async def _ask_human(self, issue: dict) -> str | None:
        """크리티컬 이슈를 사람에게 질문한다."""
        print(f"\n{'='*60}")
        print(f"🚨 [CRITICAL ISSUE]")
        print(f"   문제: {issue['description']}")
        if issue.get("suggestion"):
            print(f"   제안: {issue['suggestion']}")
        print(f"{'='*60}")

        try:
            answer = input("답변 (스킵하려면 Enter): ").strip()
            return answer if answer else None
        except EOFError:
            # 비대화형 환경에서는 로그에 기록하고 진행
            logger.warning(f"비대화형 환경. 크리티컬 이슈 로그에 기록: {issue}")
            self.state.pending_questions.append(issue)
            return None

    async def _self_heal(self, error_msg: str) -> None:
        """에러 발생 시 스스로 복구를 시도한다."""
        heal_prompt = f"""
에러가 발생했습니다. 스스로 분석하고 해결하세요.
절대로 사람에게 물어보지 마세요.

에러 메시지:
{error_msg}

수행할 작업:
1. 에러 원인 분석
2. 관련 파일 확인
3. 수정 적용
4. 테스트 재실행으로 수정 확인
"""
        await self.executor.execute(heal_prompt)

    def _update_state(self, verification: dict) -> None:
        """검증 결과로 상태를 업데이트한다."""
        total = verification.get("tests_total", 0)
        passed = verification.get("tests_passed", 0)

        self.state.test_pass_rate = (passed / total * 100) if total > 0 else 0
        self.state.lint_errors = verification.get("lint_errors", 0)
        self.state.type_errors = verification.get("type_errors", 0)
        self.state.build_success = verification.get("build_success", False)

        # 완성도 추정 (가중 평균)
        weights = {
            "test": 40,
            "lint": 15,
            "type": 15,
            "build": 30,
        }
        score = 0
        score += weights["test"] * (self.state.test_pass_rate / 100)
        score += weights["lint"] * (1 if self.state.lint_errors == 0 else 0)
        score += weights["type"] * (1 if self.state.type_errors == 0 else 0)
        score += weights["build"] * (1 if self.state.build_success else 0)
        self.state.completion_percent = score

        # 상태 저장 (재개용)
        self.state.save(self.project_path / ".claude" / "state.json")

    def _is_complete(self) -> bool:
        """완성 여부를 판단한다."""
        return (
            self.state.test_pass_rate >= COMPLETION_CRITERIA["test_pass_rate"]
            and self.state.lint_errors <= COMPLETION_CRITERIA["lint_errors"]
            and self.state.type_errors <= COMPLETION_CRITERIA["type_errors"]
            and self.state.build_success == COMPLETION_CRITERIA["build_success"]
        )

    async def _report_completion(self) -> None:
        """완성 보고 + 비크리티컬 질문 전달."""
        print(f"\n{'='*60}")
        print(f"✅ 프로젝트 {'완성' if self._is_complete() else '중간 보고'}!")
        print(f"   총 반복: {self.state.iteration}회")
        print(f"   테스트 통과율: {self.state.test_pass_rate:.1f}%")
        print(f"   린트 에러: {self.state.lint_errors}건")
        print(f"   타입 에러: {self.state.type_errors}건")
        print(f"   빌드: {'성공' if self.state.build_success else '실패'}")
        print(f"{'='*60}")

        if self.state.pending_questions:
            print(f"\n📋 비크리티컬 질문 {len(self.state.pending_questions)}건:")
            for i, q in enumerate(self.state.pending_questions, 1):
                print(f"   {i}. {q['description']}")

            print()
            try:
                answers = input("답변을 JSON으로 입력 (완료면 'done'): ").strip()
                if answers and answers != "done":
                    self.state.pending_questions.clear()
                    # 답변에 따라 수정 루프 재진입
                    await self.executor.execute(
                        f"사람의 피드백에 따라 수정하세요:\n{answers}"
                    )
                    # 수정 후 다시 검증 루프
                    self.state.completion_percent = 0  # 리셋
                    await self.run()
            except EOFError:
                logger.info("비대화형 환경. 비크리티컬 질문을 파일에 저장.")
                self._save_questions()

    def _save_questions(self) -> None:
        """비크리티컬 질문을 파일에 저장."""
        path = self.project_path / "pending_questions.json"
        with open(path, "w") as f:
            json.dump(self.state.pending_questions, f, ensure_ascii=False, indent=2)
        logger.info(f"비크리티컬 질문 저장: {path}")


class TokenLimitError(Exception):
    """토큰 한도 초과 에러."""
    pass


async def main():
    """엔트리 포인트."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m src.orchestrator.main <spec_file>")
        print("  spec_file: 확정된 스펙이 담긴 텍스트 파일 경로")
        sys.exit(1)

    spec_file = Path(sys.argv[1])
    if not spec_file.exists():
        print(f"스펙 파일이 없습니다: {spec_file}")
        sys.exit(1)

    spec = spec_file.read_text()
    project_path = str(Path.cwd())

    orchestrator = AutonomousOrchestrator(
        project_path=project_path,
        spec=spec,
    )
    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(main())
