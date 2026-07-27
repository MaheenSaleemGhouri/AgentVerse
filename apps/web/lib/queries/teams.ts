"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  addTeamMemberAction,
  createTeamAction,
  deleteTeamAction,
  duplicateTeamAction,
  executeTeamAction,
  getTeamAction,
  getTeamAnalyticsAction,
  getTeamSessionAction,
  listSessionCommunicationsAction,
  listSessionEventsAction,
  listSessionHandoffsAction,
  listTeamsAction,
  listTeamSessionsAction,
  removeTeamMemberAction,
  reorderTeamMembersAction,
  updateTeamAction,
} from "@/lib/api/actions";
import type {
  AddMemberRequest,
  CreateTeamInput,
  Team,
  TeamSession,
  UpdateTeamRequest,
} from "@/lib/api/teams";
import { queryKeys } from "@/lib/queries/keys";

/** A session that has not reached a terminal status is still moving. */
export function isSessionActive(status: string): boolean {
  return status === "queued" || status === "running";
}

export function useTeams(workspaceId: string, initialData?: Team[]) {
  return useQuery({
    queryKey: queryKeys.teams.all(workspaceId),
    queryFn: () => listTeamsAction(workspaceId),
    ...(initialData ? { initialData } : {}),
  });
}

export function useTeam(workspaceId: string, teamId: string, initialData?: Team) {
  return useQuery({
    queryKey: queryKeys.teams.detail(workspaceId, teamId),
    queryFn: () => getTeamAction(workspaceId, teamId),
    ...(initialData ? { initialData } : {}),
  });
}

export function useTeamSessions(workspaceId: string, teamId: string) {
  return useQuery({
    queryKey: queryKeys.teams.sessions(workspaceId, teamId),
    queryFn: () => listTeamSessionsAction(workspaceId, teamId),
    // Poll only while something is in flight, then stop. A dashboard
    // that keeps polling a finished team is a request per client per
    // interval, forever, for data that cannot change.
    refetchInterval: (query) =>
      query.state.data?.data.some((session) => isSessionActive(session.status)) ? 3000 : false,
  });
}

export function useTeamSession(
  workspaceId: string,
  teamId: string,
  sessionId: string,
  initialData?: TeamSession
) {
  return useQuery({
    queryKey: queryKeys.teams.session(workspaceId, teamId, sessionId),
    queryFn: () => getTeamSessionAction(workspaceId, teamId, sessionId),
    ...(initialData ? { initialData } : {}),
    refetchInterval: (query) =>
      query.state.data && isSessionActive(query.state.data.status) ? 2000 : false,
  });
}

export function useSessionEvents(workspaceId: string, teamId: string, sessionId: string) {
  return useQuery({
    queryKey: queryKeys.teams.events(workspaceId, teamId, sessionId),
    queryFn: () => listSessionEventsAction(workspaceId, teamId, sessionId),
  });
}

export function useSessionHandoffs(workspaceId: string, teamId: string, sessionId: string) {
  return useQuery({
    queryKey: queryKeys.teams.handoffs(workspaceId, teamId, sessionId),
    queryFn: () => listSessionHandoffsAction(workspaceId, teamId, sessionId),
  });
}

export function useSessionCommunications(
  workspaceId: string,
  teamId: string,
  sessionId: string
) {
  return useQuery({
    queryKey: queryKeys.teams.communications(workspaceId, teamId, sessionId),
    queryFn: () => listSessionCommunicationsAction(workspaceId, teamId, sessionId),
  });
}

export function useTeamAnalytics(workspaceId: string, teamId: string) {
  return useQuery({
    queryKey: queryKeys.teams.analytics(workspaceId, teamId),
    queryFn: () => getTeamAnalyticsAction(workspaceId, teamId),
  });
}

export function useCreateTeam(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateTeamInput) => createTeamAction(workspaceId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.teams.all(workspaceId) });
    },
    onError: () => toast.error("Could not create the team — try again."),
  });
}

export function useUpdateTeam(workspaceId: string, teamId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: UpdateTeamRequest) => updateTeamAction(workspaceId, teamId, body),
    onSuccess: (team) => {
      queryClient.setQueryData(queryKeys.teams.detail(workspaceId, teamId), team);
      void queryClient.invalidateQueries({ queryKey: queryKeys.teams.all(workspaceId) });
      toast.success("Team saved.");
    },
    onError: () => toast.error("Could not save the team — try again."),
  });
}

export function useDuplicateTeam(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (teamId: string) => duplicateTeamAction(workspaceId, teamId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.teams.all(workspaceId) });
      toast.success("Team duplicated.");
    },
    onError: () => toast.error("Could not duplicate the team — try again."),
  });
}

export function useDeleteTeam(workspaceId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (teamId: string) => deleteTeamAction(workspaceId, teamId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.teams.all(workspaceId) });
      toast.success("Team deleted.");
    },
    onError: () => toast.error("Could not delete the team — try again."),
  });
}

export function useAddTeamMember(workspaceId: string, teamId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: AddMemberRequest) => addTeamMemberAction(workspaceId, teamId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.teams.detail(workspaceId, teamId),
      });
    },
    onError: (error: Error) =>
      // The API returns a 409 with a readable reason for a duplicate
      // agent; surfacing it beats a generic failure the user cannot act
      // on.
      toast.error(
        error.message.includes("already a member")
          ? "That agent is already on this team."
          : "Could not add the agent — try again."
      ),
  });
}

export function useRemoveTeamMember(workspaceId: string, teamId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (memberId: string) => removeTeamMemberAction(workspaceId, teamId, memberId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.teams.detail(workspaceId, teamId),
      });
    },
    onError: () => toast.error("Could not remove the member — try again."),
  });
}

export function useReorderTeamMembers(workspaceId: string, teamId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (memberIds: string[]) =>
      reorderTeamMembersAction(workspaceId, teamId, memberIds),
    onSuccess: (team) => {
      queryClient.setQueryData(queryKeys.teams.detail(workspaceId, teamId), team);
    },
    onError: () => {
      // The optimistic reorder in the builder is rolled back by
      // refetching, not by replaying the previous array — the server's
      // order is the one that decides execution.
      void queryClient.invalidateQueries({
        queryKey: queryKeys.teams.detail(workspaceId, teamId),
      });
      toast.error("Could not save the new order — reverted.");
    },
  });
}

export function useExecuteTeam(workspaceId: string, teamId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (prompt: string) => executeTeamAction(workspaceId, teamId, prompt),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: queryKeys.teams.sessions(workspaceId, teamId),
      });
    },
    onError: (error: Error) =>
      // A 409 here carries the actionable reason (no members, nothing
      // published). Showing it verbatim tells the user what to fix.
      toast.error(
        error.message.includes("publish") || error.message.includes("no members")
          ? "This team cannot run yet — check its members are added and published."
          : "Could not start the team — try again."
      ),
  });
}
