# Homebrew Formula for Autonomous Dev Agent
# 사용법:
#   1. homebrew-adev 리포 생성 후:
#      brew tap uygnoey/adev
#      brew install autonomous-dev-agent
#
#   2. 또는 로컬에서 직접:
#      brew install --formula Formula/autonomous-dev-agent.rb
#
# 준비 사항:
#   - GitHub에 v0.2.0 릴리즈 태그 생성 필요
#   - sha256 해시값 업데이트 필요: shasum -a 256 <downloaded.tar.gz>
#   - resource 블록 생성 필요: brew-pip-audit 또는 poet 도구 사용
#     pip install homebrew-pypi-poet && poet autonomous-dev-agent

class AutonomousDevAgent < Formula
  include Language::Python::Virtualenv

  desc "Claude API + Agent SDK 기반 자율 무한 루프 개발 에이전트"
  homepage "https://github.com/uygnoey/autonomous-dev-agent"
  url "https://github.com/uygnoey/autonomous-dev-agent/archive/refs/tags/v0.2.0.tar.gz"
  sha256 ""  # TODO: v0.2.0 릴리즈 태그 생성 후 업데이트 - shasum -a 256 v0.2.0.tar.gz
  license "MIT"

  depends_on "python@3.12"
  depends_on "node" => :recommended  # Claude Code 설치에 필요

  # TODO: 아래 resource 블록은 poet 도구로 자동 생성해야 합니다
  # pip install homebrew-pypi-poet && poet autonomous-dev-agent
  # 생성된 resource 블록을 여기에 붙여넣으세요

  def install
    virtualenv_create(libexec, "python3.12")
    virtualenv_install_with_resources

    # CLI 엔트리포인트 심볼릭 링크
    bin.install_symlink libexec/"bin/adev"
    bin.install_symlink libexec/"bin/autonomous-dev"
  end

  def post_install
    ohai "Autonomous Dev Agent 설치 완료!"
    ohai ""
    ohai "다음 단계:"
    ohai "  1. API 키 설정: export ANTHROPIC_API_KEY=sk-ant-..."
    ohai "  2. 실행: adev"
    ohai ""
    ohai "자세한 정보: https://github.com/uygnoey/autonomous-dev-agent"
  end

  test do
    # adev는 TUI 앱이므로 --version 미지원 시 exit code 1 반환 예상
    output = shell_output("#{bin}/adev --help 2>&1", 1)
    assert_match(/adev|autonomous/i, output)
  end
end
