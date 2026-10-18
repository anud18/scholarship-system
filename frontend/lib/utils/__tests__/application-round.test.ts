import {
  applicationRoundOf,
  countGroupOrderInversions,
  findGroupOrderViolation,
  isLaterRound,
  rankingGroup,
  roundLabel,
} from "../application-round";

describe("application-round helpers", () => {
  it("labels rounds", () => {
    expect(roundLabel(1)).toBe("第一梯次");
    expect(roundLabel(2)).toBe("第二梯次");
    expect(roundLabel(11)).toBe("第11梯次");
    expect(roundLabel(2, "en")).toBe("Round 2");
  });

  it("treats a missing round as round 1", () => {
    expect(applicationRoundOf({})).toBe(1);
    expect(applicationRoundOf({ application_round: null })).toBe(1);
    expect(isLaterRound({ application_round: 1 })).toBe(false);
    expect(isLaterRound({ application_round: 2 })).toBe(true);
  });

  it("groups renewals first, then by round", () => {
    expect(rankingGroup({ is_renewal: true, application_round: 3 })).toBe(0);
    expect(rankingGroup({ application_round: 2 })).toBe(2);
    expect(rankingGroup({})).toBe(1);
  });

  it("accepts renewal → round 1 → round 2", () => {
    expect(
      findGroupOrderViolation([
        { is_renewal: true },
        { application_round: 1 },
        { application_round: 2 },
        { application_round: 2 },
      ])
    ).toBeNull();
  });

  it("rejects a later round above an earlier one", () => {
    expect(
      findGroupOrderViolation([{ application_round: 2 }, { application_round: 1 }])
    ).toBe("第二梯次申請學生的排名必須在第一梯次之後");
  });

  it("rejects a renewal below a new application", () => {
    expect(findGroupOrderViolation([{ application_round: 1 }, { is_renewal: true }])).toBe(
      "續領學生的排名必須在所有新申請學生之前"
    );
  });

  it("counts inversions so a drag may only repair a broken order", () => {
    expect(countGroupOrderInversions([{ application_round: 1 }, { application_round: 2 }])).toBe(0);
    expect(
      countGroupOrderInversions([
        { application_round: 2 },
        { application_round: 2 },
        { application_round: 1 },
      ])
    ).toBe(2);
    expect(
      countGroupOrderInversions([
        { application_round: 2 },
        { application_round: 1 },
        { application_round: 2 },
      ])
    ).toBe(1);
    expect(
      countGroupOrderInversions([{ application_round: 2 }, { application_round: 1, college_rejected: true }])
    ).toBe(0);
  });

  it("ignores college-rejected rows parked at the end", () => {
    expect(
      findGroupOrderViolation([
        { application_round: 1 },
        { application_round: 2 },
        { application_round: 1, college_rejected: true },
      ])
    ).toBeNull();
  });
});
