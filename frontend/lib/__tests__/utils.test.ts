import { cn } from "../utils";

describe("Utils", () => {
  describe("cn function", () => {
    it("should merge className strings correctly", () => {
      const result = cn("bg-blue-500", "text-white");
      expect(result).toBe("bg-blue-500 text-white");
    });

    it("should handle conditional classes", () => {
      const result = cn(
        "base-class",
        true && "conditional-class",
        false && "hidden-class"
      );
      expect(result).toBe("base-class conditional-class");
    });

    it("should merge Tailwind classes properly", () => {
      const result = cn("px-2 py-1", "px-4"); // px-4 should override px-2
      expect(result).toBe("py-1 px-4");
    });

    it("should handle arrays of classes", () => {
      const result = cn(["class1", "class2"], "class3");
      expect(result).toBe("class1 class2 class3");
    });

    it("should handle undefined and null values", () => {
      const result = cn("base-class", undefined, null, "final-class");
      expect(result).toBe("base-class final-class");
    });

    it("should handle empty inputs", () => {
      const result = cn();
      expect(result).toBe("");
    });

    it("should handle duplicate classes", () => {
      const result = cn("class1 class2", "class1 class3");
      // Tailwind merge handles duplicates, the exact behavior may vary
      expect(result).toContain("class1");
      expect(result).toContain("class2");
      expect(result).toContain("class3");
    });
  });
});
