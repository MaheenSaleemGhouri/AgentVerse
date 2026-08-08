"use client";

import { Plus } from "lucide-react";
import * as React from "react";

import type { Category } from "@/lib/marketplace/types";
import { useCreateListing } from "@/lib/queries/marketplace";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

/**
 * Create a draft listing.
 *
 * Only the fields needed to *exist* are collected here — title, summary,
 * description, category. A listing starts as a draft that nobody outside
 * the workspace can see, so this form does not need to be complete; the
 * readiness check at submit time is what enforces completeness, and it
 * reports everything missing at once rather than one field at a time.
 */
export function CreateListingDialog({
  workspaceId,
  categories,
}: {
  workspaceId: string;
  categories: Category[];
}): React.JSX.Element {
  const [open, setOpen] = React.useState(false);
  const [title, setTitle] = React.useState("");
  const [summary, setSummary] = React.useState("");
  const [description, setDescription] = React.useState("");
  const [category, setCategory] = React.useState(categories[0]?.slug ?? "");
  const create = useCreateListing(workspaceId);

  const valid = title.trim().length >= 3 && category !== "";

  async function onCreate(): Promise<void> {
    await create.mutateAsync({
      title: title.trim(),
      summary: summary.trim(),
      description: description.trim(),
      category_slug: category,
      kind: "agent",
      pricing: "free",
      price_cents: 0,
      slug: null,
    });
    setOpen(false);
    setTitle("");
    setSummary("");
    setDescription("");
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus />
          New listing
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>New listing</DialogTitle>
          <DialogDescription>
            Creates a draft only your workspace can see. Publish a version from one of your
            agents, then submit it for review.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="listing-title">Title</Label>
            <Input
              id="listing-title"
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="Release notes writer"
              minLength={3}
              maxLength={120}
              required
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="listing-summary">Summary</Label>
            <Input
              id="listing-summary"
              value={summary}
              onChange={(event) => setSummary(event.target.value)}
              placeholder="Turns merged pull requests into release notes grouped by user impact."
              maxLength={280}
            />
            <p className="text-xs text-muted-foreground">
              The one line shown in the catalog and in search results — for most people it is the
              only thing they read before deciding.
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="listing-category">Category</Label>
            <Select value={category} onValueChange={setCategory}>
              <SelectTrigger id="listing-category">
                <SelectValue placeholder="Choose a category" />
              </SelectTrigger>
              <SelectContent>
                {categories.map((entry) => (
                  <SelectItem key={entry.slug} value={entry.slug}>
                    {entry.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="listing-description">Description</Label>
            <Textarea
              id="listing-description"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
              placeholder="What it does, what it needs, and what it does not do."
              maxLength={20_000}
              rows={4}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button disabled={!valid || create.isPending} onClick={() => void onCreate()}>
            {create.isPending ? "Creating…" : "Create draft"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
