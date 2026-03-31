# Hime — Vollständiger DevOps Audit

Use `/plan` mode. This is a read-only audit — do NOT change any code yet.
Produce a single markdown report at the end: `C:\Projekte\Hime\AUDIT_REPORT.md`

---

## 1. DEPENDABOT & GITHUB SECURITY

```bash
gh auth status
gh api repos/lfl1337/Hime/dependabot/alerts --jq '.[] | {number, state, dependency: .dependency.package.name, severity: .security_advisory.severity, summary: .security_advisory.summary}' | head -50
gh api repos/lfl1337/Hime/code-scanning/alerts --jq '.[] | {number, state, rule: .rule.description, severity: .rule.security_severity_level}' | head -20
gh api repos/lfl1337/Hime/secret-scanning/alerts --jq '.[] | {number, state, secret_type}' | head -20
```

For each Dependabot alert:
- List: package name, severity (critical/high/medium/low), what it affects
- Recommendation: update command or dismiss reason
- Group by: Frontend (npm) vs Backend (pip/uv)

---

## 2. DEPENDENCY AUDIT

### Frontend (app/frontend/)
```bash
cd C:\Projekte\Hime\app\frontend
npm audit
npm outdated
```
- List all vulnerabilities by severity
- List packages more than 1 major version behind
- Check for unused dependencies: cross-reference package.json with actual imports

### Backend (app/backend/)
```bash
cd C:\Projekte\Hime\app\backend
uv pip list --outdated 2>/dev/null || pip list --outdated
```
- Check for known CVEs in installed packages
- List packages with available updates

---

## 3. SECURITY AUDIT

Scan the ENTIRE codebase for security issues:

### 3A: Input Validation
- All FastAPI endpoints: are request bodies validated with Pydantic?
- File path parameters: any path traversal risks? (../../ etc.)
- Training config endpoint: can malicious values crash the trainer?
  (e.g. negative epochs, extremely high learning rates)
- EPUB import: is the path sanitized before file operations?

### 3B: CORS & Network
- Show current CORS config in main.py — is it properly restricted?
- Are any endpoints missing authentication that should have it?
- Is the backend only listening on localhost or exposed to network?

### 3C: Secrets & Environment
- Scan for hardcoded secrets, API keys, tokens in ALL files:
  ```bash
  grep -rn "api_key\|secret\|password\|token\|API_KEY" C:\Projekte\Hime\app\ --include="*.py" --include="*.ts" --include="*.tsx" --include="*.json" | grep -v node_modules | grep -v ".lock"
  ```
- Is .env in .gitignore?
- Are there any secrets in git history?
  ```bash
  git -C C:\Projekte\Hime log --all --diff-filter=D --name-only | grep -i "env\|secret\|key"
  ```

### 3D: Process Security
- training_runner.py: is subprocess usage safe? (shell=False, no injection)
- Are training script arguments properly escaped/validated?
- Can a malicious training_config.json cause code execution?

---

## 4. CODE QUALITY AUDIT

### 4A: Error Handling
- Find all try/except blocks: are any using bare `except:` without specific exceptions?
- Are there unhandled promise rejections in the frontend? (fetch without .catch)
- Do SSE streams handle connection errors gracefully?

### 4B: Dead Code
- Find unused Python imports:
  ```bash
  cd C:\Projekte\Hime\app\backend
  find . -name "*.py" -exec python3 -c "
  import ast, sys
  with open(sys.argv[1]) as f:
      tree = ast.parse(f.read())
  # check for imported but unused names
  " {} \;
  ```
- Find unused TypeScript exports/components
- Find commented-out code blocks (>5 lines)
- Find TODO/FIXME/HACK comments and list them all

### 4C: Code Consistency
- Are all FastAPI routers using consistent response models?
- Are all frontend API calls using the typed client (training.ts)?
- Any direct fetch() calls that bypass the API client?
- Consistent error response format across all endpoints?

### 4D: Type Safety
- Any `any` types in TypeScript files?
  ```bash
  grep -rn ": any" C:\Projekte\Hime\app\frontend\src\ --include="*.ts" --include="*.tsx" | grep -v node_modules
  ```
- Any Python functions missing type hints?
- Any Pydantic models with `Any` fields?

---

## 5. PERFORMANCE AUDIT

### 5A: Frontend Bundle
```bash
cd C:\Projekte\Hime\app\frontend
npm run build 2>&1 | tail -30
```
- Total bundle size
- Largest chunks — are there obvious optimization opportunities?
- Are recharts and other heavy libs being tree-shaken?
- Is code splitting / lazy loading used for views?

### 5B: Frontend Runtime
- Count total useEffect hooks in TrainingMonitor.tsx
- Count total useState hooks — are any redundant?
- Are expensive computations wrapped in useMemo?
- React.memo usage: correct dependency arrays?

### 5C: Backend Performance
- SQLite: are queries using indexes? Show CREATE TABLE statements
- Are there N+1 query patterns?
- Is the hardware stats table growing unbounded or properly pruned?
- Are checkpoint scans (directory reads) cached or done on every request?

### 5D: Memory & Resources
- Backend: any global state that grows over time?
- Are file handles properly closed? (with statements)
- Are subprocess resources cleaned up after training stops?
- WebSocket/SSE connections: is there a max connection limit?

---

## 6. PROJECT STRUCTURE & BEST PRACTICES

- Is the project structure clean? Any files in wrong directories?
- Are all scripts executable and documented?
- Does README.md exist and is it up to date?
- Are all config files (.env.example, tsconfig, etc.) present?
- Git: any files tracked that should be in .gitignore?
  ```bash
  git -C C:\Projekte\Hime ls-files | grep -E "\.env$|node_modules|__pycache__|\.pyc|dist/|build/"
  ```

---

## REPORT FORMAT

Write the full report to `C:\Projekte\Hime\AUDIT_REPORT.md` with:

### Summary
- Total issues found by severity: Critical / High / Medium / Low / Info
- Top 5 most urgent fixes

### Detailed Findings
For each finding:
- **ID**: AUDIT-001, AUDIT-002, etc.
- **Severity**: Critical / High / Medium / Low / Info
- **Category**: Security / Quality / Performance / Dependencies
- **File**: exact file path and line number
- **Description**: what's wrong
- **Recommendation**: how to fix it
- **Effort**: Quick fix / Medium / Large refactor

### Dependabot Summary Table
| # | Package | Severity | Status | Action |
|---|---------|----------|--------|--------|

### Dependency Update Plan
Prioritized list of what to update and in what order.
