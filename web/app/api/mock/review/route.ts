import { NextResponse } from "next/server";
import { loadFixture } from "@/lib/fixtures";

export async function GET() {
  const wbs = await loadFixture("wbs_tree");
  const cards = await loadFixture("review_cards");
  return NextResponse.json({ wbs, cards });
}
