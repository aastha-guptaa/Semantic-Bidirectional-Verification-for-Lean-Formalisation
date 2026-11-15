#!/usr/bin/env python3
"""
SAGE Dual-Signal Verification & Bidirectional Semantic Equivalence Engine
Based on: "SAGE: Formalization with Semantic Correction" (Hirtz et al., 2026)
and Bidirectional Equivalence (BEq) protocols for Lean 4 formalizations.
"""

import sys
import os
import json
import re
import subprocess
import urllib.request
from pathlib import Path

# OpenMathOS Endpoint Configuration
API_URL = "https://os.openmathmodel.org/v1/chat/completions"
DEFAULT_MODEL = "moonshotai/kimi-k3.1-pro"

# SAGE Table 10 Cutoffs
SAGE_CUTOFFS = {
    "semantic_match": (">=4", lambda s: s >= 4),
    "missing": ("<=1", lambda s: s <= 1),
    "extra": ("<=1", lambda s: s <= 1),
    "wrong": ("=0", lambda s: s == 0),
    "exactness": (">=1", lambda s: s >= 1),
    "naturality": (">=3", lambda s: s >= 3),
    "descriptive_precision": (">=3", lambda s: s >= 3)
}

def get_api_key() -> str:
    """Retrieve the OpenMathOS model API key from environment or local .env files."""
    key = os.environ.get("OPENMATHOS_MODEL_KEY", "").strip() or os.environ.get("OPENMATHOS_API_KEY", "").strip()
    if not key:
        search_dirs = [
            Path.cwd(),
            Path(__file__).resolve().parent,
            Path(__file__).resolve().parents[1],
            Path(__file__).resolve().parents[1] / "interrupt-harness"
        ]
        for d in search_dirs:
            env_file = d / ".env"
            if env_file.exists():
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    if line.startswith("OPENMATHOS_MODEL_KEY="):
                        key = line.partition("=")[2].strip()
                        break
                    elif line.startswith("OPENMATHOS_API_KEY="):
                        key = line.partition("=")[2].strip()
                        break
                if key:
                    break
    if not key:
        raise ValueError(
            "OpenMathOS Model API Key not found. Please set OPENMATHOS_MODEL_KEY environment variable "
            "or create a local .env file with OPENMATHOS_MODEL_KEY=nuc_ak_..."
        )
    return key

def call_open_math_os(messages, model=None, temperature=0.1, max_tokens=24576):
    """Call the OpenMathOS LLM API."""
    model = model or os.environ.get("OPENMATHOS_MODEL", DEFAULT_MODEL)
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    headers = {
        "Authorization": f"Bearer {get_api_key()}",
        "Content-Type": "application/json",
        "User-Agent": "OpenMathOS-Client/1.0"
    }
    req = urllib.request.Request(API_URL, data=json.dumps(payload).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
    
    choice = res["choices"][0]
    content = choice["message"].get("content", "")
    reasoning = choice["message"].get("reasoning", "")
    if not content and reasoning:
        return reasoning
    return content

def strip_lean_comments_and_strings(code: str) -> str:
    """Strip block comments, line comments, and string literals to prevent AST spoofing."""
    code = re.sub(r'/-(?:[^-]|-(?!/))*-/', '', code, flags=re.DOTALL)
    code = re.sub(r'--.*$', '', code, flags=re.MULTILINE)
    code = re.sub(r'"(?:\\.|[^"\\])*"', '""', code)
    return code

def audit_single_sorry(lean_code: str):
    """Enforce the Single-Sorry Contract: count actual placeholder axioms."""
    cleaned = strip_lean_comments_and_strings(lean_code)
    placeholders = re.findall(r'\b(sorry|admit|proof_wanted)\b', cleaned)
    count = len(placeholders)
    valid = (count <= 1)
    return {
        "placeholder_count": count,
        "placeholders": placeholders,
        "satisfies_single_sorry": valid
    }

def find_lake_root(start_path: Path) -> Path:
    """Find the root directory of the Lean project containing lakefile."""
    current = start_path.resolve()
    if current.is_file():
        current = current.parent
    for parent in [current, *current.parents]:
        if (parent / "lakefile.toml").exists() or (parent / "lakefile.lean").exists():
            return parent
    return current

def run_lean_compiler(file_path: str):
    """Execute Lean 4 compiler to check syntactic and type-theoretic correctness."""
    target = Path(file_path).resolve()
    root_dir = find_lake_root(target)
    
    env = os.environ.copy()
    possible_elan = [root_dir / ".elan" / "bin", Path.home() / ".elan" / "bin"]
    for e in possible_elan:
        if e.exists():
            env["PATH"] = f"{e}:{env.get('PATH', '')}"
            env["ELAN_HOME"] = str(e.parent)
            break
    
    cmd = ["lake", "env", "lean", str(target)]
    try:
        proc = subprocess.run(cmd, cwd=str(root_dir), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        output = (proc.stdout + "\n" + proc.stderr).strip()
        compiled = (proc.returncode == 0)
    except FileNotFoundError:
        cmd = ["lean", str(target)]
        proc = subprocess.run(cmd, cwd=str(root_dir), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        output = (proc.stdout + "\n" + proc.stderr).strip()
        compiled = (proc.returncode == 0)
    
    errors = []
    for line in output.split("\n"):
        line = line.strip()
        if "error:" in line or "error(lean" in line:
            errors.append(line)
            
    return {
        "compiled": compiled,
        "return_code": proc.returncode,
        "total_errors": len(errors),
        "primary_error": errors[0] if errors else None,
        "first_k_errors": errors[:5],
        "raw_output": output
    }

def back_translate(lean_code: str) -> str:
    """Stateless back-translation: reconstruct informal statement strictly from Lean code."""
    system_prompt = (
        "You are an expert mathematical translator and logician. "
        "Your task is BACK-TRANSLATION (Formal to Informal): read the given Lean 4 code "
        "and reconstruct the exact mathematical statement, hypotheses, quantifiers, and "
        "conclusions in rigorous, formal mathematical natural language (English). "
        "Do NOT guess external context: translate strictly what is declared in the Lean 4 formalization. "
        "Clearly list: 1) Ambient objects and typeclasses, 2) Exact premises and binders, 3) The central conclusion/equality."
    )
    user_prompt = f"Here is the Lean 4 formal code:\n\n```lean\n{lean_code}\n```\n\nProvide the rigorous natural language reconstruction of this theorem."
    
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    return call_open_math_os(messages)

def extract_json(raw: str):
    """Safely parse JSON from LLM response text or code blocks."""
    raw = raw.strip()
    try:
        return json.loads(raw)
    except Exception:
        pass
    match = re.search(r'(\{[\s\S]*\})', raw)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            pass
    for block in re.findall(r'```(?:json)?\s*([\s\S]*?)\s*```', raw):
        try:
            return json.loads(block)
        except Exception:
            continue
    raise ValueError(f"Could not parse JSON from response:\n{raw}")

def evaluate_sage_semantic(source_nl: str, formal_lean: str, back_translated_nl: str):
    """Perform multi-dimensional SAGE semantic evaluation and Bidirectional Equivalence check."""
    system_prompt = """You are the SAGE Semantic Rater and Bidirectional Equivalence Auditor.
You audit the Lean 4 formalization against the original informal mathematical statement.

Evaluate the formalization across the exact SAGE multi-dimensional criteria (Table 10):
1. Modular Component Matching:
   - "missing" (Scale 0-3): Necessary components/hypotheses dropped. 0=none, 1=minor/implicit, 2=significant, 3=severe. (Cutoff: <=1)
   - "wrong" (Scale 0-2): Components mapped to incorrect, inverted, or flawed representations. 0=none, 1=minor misalignment, 2=major error. (Cutoff: =0)
   - "extra" (Scale 0-4): Spurious components or smuggled hypotheses introduced that restrict scope or trivialize the claim. (Cutoff: <=1)
2. Holistic Mathematical Equivalence:
   - "semantic_match" (Scale 0-4): Translational equivalence between formal and informal. 4=complete fidelity, 0=unrelated. (Cutoff: >=4)
   - "exactness" (Scale 0-3): Structural alignment with informal source without unnecessary reformulations. (Cutoff: >=1)
3. Code Implementation Quality:
   - "naturality" (Scale 0-4): Idiomatic Lean 4 / Mathlib conventions. (Cutoff: >=3)
   - "descriptive_precision" (Scale 0-4): Conceptual depth, avoiding trivialized stubs. (Cutoff: >=3)
4. Bidirectional Equivalence (BEq):
   - "bidirectional_equivalence" (boolean): True iff S_NL <=> S_NL' (the back-translated Lean statement is logically equivalent in both directions to the original natural language statement).

Return STRICTLY a JSON object with this schema:
{
  "scores": {
    "semantic_match": int,
    "missing": int,
    "extra": int,
    "wrong": int,
    "exactness": int,
    "naturality": int,
    "descriptive_precision": int
  },
  "bidirectional_equivalence": bool,
  "component_breakdown": {
    "missing_components": [str],
    "wrong_components": [str],
    "extra_components": [str]
  },
  "rationale": str,
  "repair_recommendations": [str]
}
"""

    user_prompt = f"""
ORIGINAL INFORMAL STATEMENT (S_NL):
\"\"\"{source_nl}\"\"\"

LEAN 4 FORMALIZATION (S_F):
```lean
{formal_lean}
```

BACK-TRANSLATED STATEMENT FROM LEAN (S_NL'):
\"\"\"{back_translated_nl}\"\"\"

Perform the rigorous SAGE Semantic Audit. Keep your internal reasoning under 1500 tokens and ensure you output the complete JSON object strictly matching the schema.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt}
    ]
    raw = call_open_math_os(messages, max_tokens=24576)
    return extract_json(raw)

def verify_file(file_path: str, source_nl: str):
    """Run full dual-signal verification pipeline."""
    print(f"\n=======================================================")
    print(f"  SAGE VERIFICATION ENGINE: {os.path.basename(file_path)}")
    print(f"=======================================================")
    
    with open(file_path, "r", encoding="utf-8") as f:
        lean_code = f.read()
        
    # 1. Compiler Check
    print("[1/4] Running Lean 4 Typechecker & Compiler Verifier...")
    compiler_res = run_lean_compiler(file_path)
    compile_pass = compiler_res["compiled"]
    print(f"      Compiler Status: {'PASS (Exit Code 0)' if compile_pass else 'FAIL'}")
    if not compile_pass:
        print(f"      Primary Error: {compiler_res['primary_error']}")
        
    # 2. Single-Sorry Contract Check
    print("[2/4] Auditing Single-Sorry Contract & Stubs...")
    sorry_res = audit_single_sorry(lean_code)
    sorry_pass = sorry_res["satisfies_single_sorry"]
    print(f"      Placeholder Count: {sorry_res['placeholder_count']} {sorry_res['placeholders']}")
    print(f"      Single-Sorry Contract: {'PASS' if sorry_pass else 'FAIL (Multiple Sorries / Stubs)'}")
    
    # 3. Back-Translation (Formal -> Informal)
    print("[3/4] Performing Bidirectional Back-Translation (S_F -> S_NL')...")
    back_cache_file = f"{file_path}.back_translation.txt"
    if os.path.exists(back_cache_file) and os.path.getsize(back_cache_file) > 10:
        with open(back_cache_file, "r", encoding="utf-8") as f:
            back_nl = f.read()
        print("      (Loaded cached back-translation from disk)")
    else:
        back_nl = back_translate(lean_code)
        with open(back_cache_file, "w", encoding="utf-8") as f:
            f.write(back_nl)
    print("      Reconstructed Informal Mathematics (Preview):")
    for line in back_nl.strip().split("\n")[:4]:
        print(f"        {line}")
    if len(back_nl.strip().split("\n")) > 4:
        print("        ...")
        
    # 4. Multi-Dimensional Semantic Gate (Sage-SM) + BEq
    print("[4/4] Evaluating SAGE Multi-Dimensional Rubric & Bidirectional Equivalence...")
    semantic_res = evaluate_sage_semantic(source_nl, lean_code, back_nl)
    
    # Evaluate SAGE cutoffs
    scores = semantic_res.get("scores", {})
    gate_failures = []
    for dim, (condition, check_fn) in SAGE_CUTOFFS.items():
        val = scores.get(dim, 0)
        if not check_fn(val):
            gate_failures.append(f"{dim} (Score: {val}, Required: {condition})")
            
    sage_sm_pass = (len(gate_failures) == 0)
    beq_pass = semantic_res.get("bidirectional_equivalence", False)
    
    overall_pass = compile_pass and sorry_pass and sage_sm_pass and beq_pass
    
    # Compile full report
    report = {
        "file": file_path,
        "compile_verifier": compiler_res,
        "single_sorry_contract": sorry_res,
        "back_translation": back_nl,
        "semantic_rater": semantic_res,
        "sage_gate": {
            "sage_sm_pass": sage_sm_pass,
            "gate_failures": gate_failures,
            "beq_pass": beq_pass
        },
        "joint_verdict": {
            "compile": compile_pass,
            "sage_sm": sage_sm_pass,
            "beq": beq_pass,
            "overall_status": "PASS" if overall_pass else "FAIL"
        }
    }
    
    return report

def main():
    if len(sys.argv) < 2:
        prog = sys.argv[0]
        print(f"Usage: {prog} <lean_file> [source_nl_file]")
        sys.exit(1)
        
    raw_path = sys.argv[1]
    p = Path(raw_path)
    if not p.exists():
        # Case-insensitive and fuzzy resolver across the repo
        target_name = p.name.lower()
        candidates = [
            f for f in Path.cwd().glob("**/*.lean")
            if f.name.lower() == target_name or target_name.replace(".lean", "") in f.name.lower()
        ]
        if candidates:
            p = candidates[0]
            print(f"[NOTE] Resolved '{raw_path}' to existing file: {p}")
        else:
            print(f"Error: Lean file '{raw_path}' does not exist.")
            sys.exit(1)
    lean_file = str(p)
    
    default_source = (
        "When G and A are discrete, it is not hard to see, using the techniques of Section 5.3, "
        "that the composition\n"
        "H^n_{gp}(G, A) -> H^n(\\bar{B}G, A) -> H^n(BG, A) -> H^n(B_n G, A)\n"
        "is the same as \\alpha_n."
    )
    
    if len(sys.argv) >= 3 and os.path.exists(sys.argv[2]):
        with open(sys.argv[2], "r", encoding="utf-8") as f:
            source_nl = f.read()
    else:
        source_nl = default_source
        
    report = verify_file(lean_file, source_nl)
    
    out_json = f"{lean_file}.verification.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)
        
    print("\n" + "="*55)
    print("           SAGE VERIFICATION SUMMARY REPORT")
    print("="*55)
    print(f"File: {report['file']}")
    print(f"Compiler Check (Compile):          {'[PASS]' if report['joint_verdict']['compile'] else '[FAIL]'}")
    print(f"Single-Sorry Contract:             {'[PASS]' if report['single_sorry_contract']['satisfies_single_sorry'] else '[FAIL]'}")
    print(f"In-Loop Semantic Gate (Sage-SM):    {'[PASS]' if report['joint_verdict']['sage_sm'] else '[FAIL]'}")
    print(f"Bidirectional Equivalence (BEq):    {'[PASS]' if report['joint_verdict']['beq'] else '[FAIL]'}")
    print(f"JOINT VERDICT (Compile ∧ Sage-SM):  {'>>> PASS <<<' if report['joint_verdict']['overall_status'] == 'PASS' else '>>> FAIL <<<'}")
    print("-" * 55)
    print("Dimension Scores (vs SAGE Table 10 Cutoffs):")
    for dim, (cond, _) in SAGE_CUTOFFS.items():
        score = report['semantic_rater']['scores'].get(dim, "N/A")
        print(f"  • {dim:22}: {score} (Req: {cond})")
    print("-" * 55)
    if report['sage_gate']['gate_failures']:
        print("Failing Dimensions:")
        for fail in report['sage_gate']['gate_failures']:
            print(f"  [X] {fail}")
    print(f"Rationale:\n{report['semantic_rater']['rationale']}")
    if report['semantic_rater']['repair_recommendations']:
        print("\nRepair Recommendations:")
        for rec in report['semantic_rater']['repair_recommendations']:
            print(f"  - {rec}")
    print("="*55)
    print(f"Full JSON report saved to: {out_json}")

if __name__ == "__main__":
    main()
