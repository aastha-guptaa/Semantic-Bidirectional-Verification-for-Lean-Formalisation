# Semantic Bidirectional Verification for Lean 4 Formalization

A dual-signal verification and bidirectional semantic equivalence engine for Lean 4 mathematical formalizations, implementing the **SAGE** framework (*"SAGE: Formalization with Semantic Correction"*, Hirtz et al., 2026).

---

## 1. Motivation: The "Typechecker Blind Spot"

Modern interactive theorem provers (such as Lean 4) verify internal deductive consistency with absolute rigor. However, compiler success (`exit code 0`) only guarantees that the formal proof proves the formal theorem statement—it provides **zero guarantee that the formal statement faithfully represents the target mathematical paper**.

In automated and human formalizations, subtle flaws can bypass the compiler:
1. **Hypothesis Smuggling**: Adding unstated premises or conditions as function arguments or typeclass assumptions that restrict scope or trivialize the claim.
2. **Domain Mutation**: Inverting arrows, mutating topological groups into discrete groups, or swapping mathematical objects for weakened algebraic approximations.
3. **Mock Stubs & Axiom Inflation**: Concealing unproved lemmas behind multiple `sorry` or `axiom` declarations.

This engine establishes an independent, automated verification gate enforcing the **Joint Verdict**:
$$\text{Verified} = \text{Compile} \land \text{Single-Sorry Contract} \land \text{Sage-SM} \land \text{BEq}$$

---

## 2. 4-Phase Verification Architecture

```
                 [ Lean 4 File (S_F) ]
                           │
       ┌───────────────────┴───────────────────┐
       ▼                                       ▼
  [ Phase 1: Compiler Check ]             [ Phase 2: Single-Sorry Audit ]
  - lake env lean                         - Strip comments & string literals
  - Root-error de-cascading               - Count (sorry|admit|proof_wanted) <= 1
       │                                       │
       └───────────────────┬───────────────────┘
                           ▼
              [ Phase 3: Back-Translation ]
              - Blind Stateless Re-construction: S_F -> S_NL'
              - Zero access to original informal source (anti-bias)
                           │
                           ▼
          [ Phase 4: SAGE Multi-Dimensional Gate & BEq ]
          - Table 10 Rubric Scoring
          - Bidirectional Equivalence: S_NL <=> S_NL'
                           │
                           ▼
             [ Joint Verification Verdict ]
```

### Phase 1: Compiler Verification (`Compile`)
Executes `lake env lean` within the project environment, incorporating local dependencies and `.lake` libraries into `LEAN_PATH`. If compilation fails, the error de-cascader isolates the primary root error from secondary downstream cascades.

### Phase 2: Single-Sorry Contract (`Single-Sorry`)
Strips all Lean block comments (`/- ... -/`), docstrings (`/-- ... -/`), line comments (`-- ...`), and string literals from the source code to prevent AST spoofing. It audits remaining unproved placeholders (`sorry`, `admit`, `proof_wanted`), enforcing:
$$\text{Placeholder Count} \le 1$$

### Phase 3: Blind Stateless Back-Translation ($S_F \to S_{\mathrm{NL}}^\prime$)
To eliminate confirmation bias, the engine extracts the formal declarations and tasks an independent LLM reasoner with reconstructing the formal code into rigorous, formal mathematical English. The back-translator has **no access** to the original informal source prompt.

### Phase 4: Multi-Dimensional Semantic Gate (`Sage-SM`) & Bidirectional Equivalence (`BEq`)
The original informal statement ($S_{\mathrm{NL}}$) and the reconstructed statement ($S_{\mathrm{NL}}^\prime$) are cross-audited against the exact SAGE Table 10 rubrics and cutoffs:

| Dimension | Description | Cutoff |
| :--- | :--- | :---: |
| **`wrong`** | Components mapped to incorrect, inverted, or flawed representations. | **$= 0$ (Zero Tolerance)** |
| **`missing`** | Necessary components, quantifiers, or hypotheses dropped. | **$\le 1$** |
| **`extra`** | Spurious components or smuggled hypotheses introduced. | **$\le 1$** |
| **`exactness`** | Structural alignment with informal source without unnecessary reformulations. | **$\ge 1$** |
| **`naturality`** | Idiomatic Lean 4 / Mathlib conventions. | **$\ge 3$** |
| **`descriptive_precision`** | Conceptual depth, avoiding trivialized or vacuous stubs. | **$\ge 3$** |
| **`semantic_match`** | Translational equivalence between formal and informal. | **$\ge 4$** |
| **`BEq`** | **Bidirectional Equivalence**: True iff $S_{\mathrm{NL}} \iff S_{\mathrm{NL}}^\prime$ holds in both directions. | **True** |

---

## 3. Installation & Requirements

- **Python**: $\ge 3.10$ (standard library only; no external Python packages required)
- **Lean 4**: Any active Lean 4 / Mathlib environment with `lake`
- **OpenMathOS API**: Access key for the semantic evaluation model (e.g. `moonshotai/kimi-k3.1-pro`)

---

## 4. Configuration

Set your OpenMathOS model API key via environment variable:
```bash
export OPENMATHOS_MODEL_KEY="nuc_ak_your_key_here"
```

Or configure via a local `.env` file (which is git-ignored):
```bash
cp .env.example .env
# Edit .env and enter your key: OPENMATHOS_MODEL_KEY=nuc_ak_...
```

*(Optional: Set `OPENMATHOS_MODEL` to override the default rater model).*

---

## 5. Usage

### Verifying a Single Lean 4 File
```bash
python3 verify_formalization.py path/to/Theorem.lean
```

### Verifying with a Custom Mathematical Source Statement
```bash
python3 verify_formalization.py path/to/Theorem.lean path/to/informal_source.txt
```

### Verifying an Entire Folder / Submodule
```bash
python3 verify_formalization.py path/to/FormalizationFolder/
```
In folder mode, the engine audits every `.lean` file in the directory, produces individual `.verification.json` audit reports, and displays an aggregate compliance summary.

---

## 6. Output & Audit Artifacts

The tool produces a structured terminal report and writes a permanent JSON audit artifact (`<file>.verification.json`):

```json
{
  "file": "path/to/Theorem.lean",
  "compile_verifier": {
    "compiled": true,
    "total_errors": 0
  },
  "single_sorry_contract": {
    "placeholder_count": 0,
    "satisfies_single_sorry": true
  },
  "semantic_rater": {
    "scores": {
      "semantic_match": 4,
      "missing": 0,
      "extra": 0,
      "wrong": 0,
      "exactness": 2,
      "naturality": 4,
      "descriptive_precision": 4
    },
    "bidirectional_equivalence": true,
    "rationale": "...",
    "repair_recommendations": []
  },
  "joint_verdict": {
    "compile": true,
    "sage_sm": true,
    "beq": true,
    "overall_status": "PASS"
  }
}
```

---

## References

- Hirtz et al., *"SAGE: Formalization with Semantic Correction"*, 2026.
- The Mathlib Community, *"Lean 4 & Mathlib"*, 2024.
