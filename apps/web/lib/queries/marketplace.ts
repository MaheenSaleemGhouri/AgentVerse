"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  browseListingsAction,
  createListingAction,
  installListingAction,
  listMyListingsAction,
  listReviewsAction,
  publishListingVersionAction,
  shareListingAction,
  startMarketplaceCheckoutAction,
  submitListingAction,
  submitReviewAction,
  unlistListingAction,
  withdrawReviewAction,
} from "@/lib/api/actions";
import type {
  CatalogFilters,
  CreateListingRequest,
  Listing,
  ListingPage,
  PublishVersionRequest,
  Review,
} from "@/lib/marketplace/types";
import { queryKeys } from "@/lib/queries/keys";

export function useCatalog(filters: CatalogFilters, initialData?: ListingPage) {
  return useQuery<ListingPage>({
    queryKey: queryKeys.marketplace.catalog({
      q: filters.q,
      category: filters.category,
      official: filters.official,
      free: filters.free,
      sort: filters.sort,
      page: filters.page,
    }),
    queryFn: () => browseListingsAction(filters),
    // Paging or changing a filter keeps the previous grid on screen
    // instead of collapsing to a skeleton and back — the page height
    // stays stable, so the layout does not jump under the cursor.
    placeholderData: keepPreviousData,
    ...(initialData ? { initialData } : {}),
  });
}

export function useReviews(slug: string, initialData?: Review[]) {
  return useQuery<Review[]>({
    queryKey: queryKeys.marketplace.reviews(slug),
    queryFn: () => listReviewsAction(slug),
    ...(initialData ? { initialData } : {}),
  });
}

export function useMyListings(workspaceId: string, initialData?: Listing[]) {
  return useQuery<Listing[]>({
    queryKey: queryKeys.marketplace.mine(workspaceId),
    queryFn: () => listMyListingsAction(workspaceId),
    ...(initialData ? { initialData } : {}),
  });
}

export function useInstallListing(workspaceId: string) {
  return useMutation({
    mutationFn: (input: { slug: string; versionNumber?: number | null; name?: string | null }) =>
      installListingAction(workspaceId, input.slug, {
        version_number: input.versionNumber ?? null,
        name: input.name ?? null,
      }),
    onSuccess: (install) => {
      // `created: false` means an identical install already existed and
      // the same agent came back. Saying so is the difference between
      // "it worked" and "it did nothing, twice" — the same distinction
      // the CLI draws.
      toast.success(
        install.created
          ? `Installed as a new agent (v${String(install.version_number)}).`
          : "Already installed — opening the agent you have.",
      );
    },
    onError: () => toast.error("Could not install this listing. Try again."),
  });
}

/**
 * Starts Stripe Checkout for a premium listing. The caller (the install
 * dialog) is expected to have already routed a free listing to
 * `useInstallListing` instead — this mutation exists only for the
 * priced path.
 */
export function useStartMarketplaceCheckout(workspaceId: string) {
  return useMutation({
    mutationFn: (slug: string) => startMarketplaceCheckoutAction(workspaceId, slug),
    onError: () => toast.error("Could not start checkout for this listing. Try again."),
  });
}

export function useShareListing(workspaceId: string) {
  return useMutation({
    mutationFn: (slug: string) => shareListingAction(workspaceId, slug),
  });
}

export function useSubmitReview(workspaceId: string, slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { rating: number; body: string }) =>
      submitReviewAction(workspaceId, slug, input),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.marketplace.reviews(slug) });
      toast.success("Review published.");
    },
    onError: (error: Error) =>
      // The one refusal worth naming precisely: the API blocks reviewing
      // your own listing server-side, and "try again" would be wrong
      // advice for it.
      toast.error(
        error.message.includes("own")
          ? "You cannot review your own listing."
          : "Could not save your review.",
      ),
  });
}

export function useWithdrawReview(workspaceId: string, slug: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => withdrawReviewAction(workspaceId, slug),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.marketplace.reviews(slug) });
      toast.success("Review withdrawn.");
    },
    onError: () => toast.error("Could not withdraw your review."),
  });
}

export function useCreateListing(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateListingRequest) => createListingAction(workspaceId, body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.marketplace.mine(workspaceId) });
      toast.success("Draft created. Publish a version, then submit it for review.");
    },
    onError: (error: Error) =>
      toast.error(
        error.message.includes("slug") ? "That slug is taken." : "Could not create the listing.",
      ),
  });
}

export function usePublishVersion(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { slug: string; body: PublishVersionRequest }) =>
      publishListingVersionAction(workspaceId, input.slug, input.body),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.marketplace.mine(workspaceId) });
      toast.success("Version published.");
    },
    onError: () => toast.error("Could not publish this version."),
  });
}

export function useSubmitListing(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => submitListingAction(workspaceId, slug),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.marketplace.mine(workspaceId) });
      toast.success("Submitted for review.");
    },
    onError: (error: Error) =>
      // Readiness failures come back as a list of what is missing, and
      // that list is the actual remediation — showing it beats "could
      // not submit".
      toast.error(error.message || "Could not submit this listing."),
  });
}

export function useUnlistListing(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (slug: string) => unlistListingAction(workspaceId, slug),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.marketplace.mine(workspaceId) });
      toast.success("Unlisted. Existing installs keep working.");
    },
    onError: () => toast.error("Could not unlist this listing."),
  });
}
