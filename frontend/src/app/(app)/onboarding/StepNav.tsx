"use client";

import Link from "next/link";
import { secondaryButtonClass, buttonClass } from "@/components/settings/shared";

export function StepNav({
  back,
  next,
  nextLabel = "Next",
}: {
  back?: string;
  next?: string;
  nextLabel?: string;
}) {
  return (
    <div className="flex justify-between mt-8">
      {back ? (
        <Link href={back} className={secondaryButtonClass}>
          Back
        </Link>
      ) : (
        <span />
      )}
      {next && (
        <Link href={next} className={buttonClass}>
          {nextLabel}
        </Link>
      )}
    </div>
  );
}
