# Homebrew formula for agent-team, for a tap (github.com/lakeba/homebrew-tap, Formula/agent-team.rb).
# After each PyPI release: update url and sha256, then fill in the dependencies' resources with
#   brew update-python-resources Formula/agent-team.rb
# Users install with: brew install lakeba/tap/agent-team
class AgentTeam < Formula
  include Language::Python::Virtualenv

  desc "Configurable team of AI agents that plans, builds, reviews and ships through GitHub"
  homepage "https://github.com/lakeba/agent-team"
  url "https://files.pythonhosted.org/packages/source/a/agent-team/agent_team-0.5.0.tar.gz"
  sha256 "REPLACE_WITH_THE_SDIST_SHA256"
  license "MIT"

  depends_on "python@3.12"

  # resource blocks for anthropic and its dependencies go here (brew update-python-resources).

  def install
    virtualenv_install_with_resources
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/agent-team --version")
  end
end
