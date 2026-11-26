"""
Academic Blood Group & Component Compatibility Rules.
NOTE: Simplified, clearly documented academic compatibility matrix for DBMS demonstration only.
Do NOT present or use this module as a clinically validated transfusion decision system.
"""
from typing import Dict, List, Tuple

from app.models.enums import BloodComponent, BloodGroup, RhFactor

ACADEMIC_DISCLAIMER = (
    "Simplified academic blood compatibility rules for demonstration only; "
    "not a clinically validated transfusion decision system."
)

# Default shelf lives (in days) and component volumes (in mL) for component separation
COMPONENT_SPECS: Dict[str, Tuple[int, int]] = {
    BloodComponent.WHOLE_BLOOD.value: (35, 450),
    BloodComponent.RBC.value: (42, 250),
    BloodComponent.PLATELETS.value: (5, 60),
    BloodComponent.FFP.value: (365, 200),
    BloodComponent.CRYOPRECIPITATE.value: (365, 40),
}

# ABO compatibility for Red Blood Cells & Whole Blood: recipient -> ordered compatible donor groups
RBC_ABO_COMPATIBILITY: Dict[str, List[str]] = {
    BloodGroup.O.value: [BloodGroup.O.value],
    BloodGroup.A.value: [BloodGroup.A.value, BloodGroup.O.value],
    BloodGroup.B.value: [BloodGroup.B.value, BloodGroup.O.value],
    BloodGroup.AB.value: [BloodGroup.AB.value, BloodGroup.A.value, BloodGroup.B.value, BloodGroup.O.value],
}

# Reverse ABO compatibility for Plasma (FFP & Cryoprecipitate): recipient -> ordered compatible donor groups
PLASMA_ABO_COMPATIBILITY: Dict[str, List[str]] = {
    BloodGroup.O.value: [BloodGroup.O.value, BloodGroup.A.value, BloodGroup.B.value, BloodGroup.AB.value],
    BloodGroup.A.value: [BloodGroup.A.value, BloodGroup.AB.value],
    BloodGroup.B.value: [BloodGroup.B.value, BloodGroup.AB.value],
    BloodGroup.AB.value: [BloodGroup.AB.value],
}


def get_compatible_donor_types(
    recipient_group: str,
    recipient_rh: str,
    component_type: str,
    allow_substitutes: bool = True,
) -> List[Tuple[str, str]]:
    """
    Returns an ordered list of compatible (blood_group, rh_factor) donor types
    for the requested component, placing the exact match first.
    """
    exact = (recipient_group, recipient_rh)
    if not allow_substitutes:
        return [exact]

    if component_type in (BloodComponent.FFP.value, BloodComponent.CRYOPRECIPITATE.value):
        abo_candidates = PLASMA_ABO_COMPATIBILITY.get(recipient_group, [recipient_group])
        rh_candidates = (
            [RhFactor.POSITIVE.value, RhFactor.NEGATIVE.value]
            if recipient_rh == RhFactor.POSITIVE.value
            else [RhFactor.NEGATIVE.value, RhFactor.POSITIVE.value]
        )
    elif component_type == BloodComponent.PLATELETS.value:
        abo_candidates = PLASMA_ABO_COMPATIBILITY.get(recipient_group, [recipient_group])
        rh_candidates = (
            [RhFactor.POSITIVE.value, RhFactor.NEGATIVE.value]
            if recipient_rh == RhFactor.POSITIVE.value
            else [RhFactor.NEGATIVE.value]
        )
    else:
        # RBC & WHOLE_BLOOD
        abo_candidates = RBC_ABO_COMPATIBILITY.get(recipient_group, [recipient_group])
        rh_candidates = (
            [RhFactor.POSITIVE.value, RhFactor.NEGATIVE.value]
            if recipient_rh == RhFactor.POSITIVE.value
            else [RhFactor.NEGATIVE.value]
        )

    ordered: List[Tuple[str, str]] = [exact]
    for grp in abo_candidates:
        for rh in rh_candidates:
            pair = (grp, rh)
            if pair not in ordered:
                ordered.append(pair)
    return ordered


def is_unit_compatible(
    donor_group: str,
    donor_rh: str,
    donor_component: str,
    recipient_group: str,
    recipient_rh: str,
    requested_component: str,
) -> bool:
    """Checks whether a candidate unit matches component type and academic ABO/Rh compatibility."""
    if donor_component != requested_component:
        return False
    compatible_pairs = get_compatible_donor_types(
        recipient_group=recipient_group,
        recipient_rh=recipient_rh,
        component_type=requested_component,
        allow_substitutes=True,
    )
    return (donor_group, donor_rh) in compatible_pairs
