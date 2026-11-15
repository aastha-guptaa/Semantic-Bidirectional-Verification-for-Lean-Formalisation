import Mathlib

/-!
# Sample Theorem: Group Homomorphism Identity
A minimal example demonstrating Lean 4 code to be audited by the SAGE verification layer.
-/

theorem group_hom_one {G H : Type*} [Group G] [Group H] (f : G →* H) :
    f 1 = 1 := by
  exact map_one f
