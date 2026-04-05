export interface Meeting {
  id: string;
  user_id: string;
  title: string | null;
  status: 'pending' | 'processing' | 'processed' | 'failed';
  summary: string | null;
  processed_at: string | null;
  created_at: string;
  action_items_count: number;
  decisions_count: number;
}

export interface ActionItem {
  id: string;
  user_id: string;
  meeting_id: string | null;
  title: string;
  owner: string;
  deadline: string | null;
  priority: number;
  complexity: number;
  duration_minutes: number;
  status: 'pending' | 'scheduled' | 'done' | 'dropped';
  calendar_event_id: string | null;
  task_id: string | null;
  created_at: string;
}

export interface CognitiveState {
  id: string;
  owner: string;
  load_score: number;
  capacity: number;
  overload_flag: boolean;
  context_switches: number;
  load_percentage: number;
  calculated_at: string;
}

export interface DecisionLog {
  id: string;
  meeting_id: string | null;
  agent: 'transcript' | 'cognitive' | 'scheduler' | 'execution' | 'orchestrator';
  decision: string;
  reason: string;
  metadata: Record<string, unknown> | null;
  timestamp: string;
}

export interface DashboardStats {
  meetings_today: number;
  total_action_items: number;
  user_load_percentage: number;
  total_decisions: number;
  overloaded_owners: string[];
}

export interface DashboardData {
  meetings: Meeting[];
  action_items: ActionItem[];
  cognitive_states: CognitiveState[];
  decisions: DecisionLog[];
  stats: DashboardStats;
}

export interface ProcessMeetingResponse {
  success: boolean;
  message: string;
  meeting_id: string;
  action_items_created: number;
  events_created: number;
  tasks_created: number;
  overloaded_owners: string[];
  decisions: DecisionLog[];
}

export interface AddTaskRequest {
  title: string;
  owner: string;
  duration_minutes: number;
  priority: number;
  complexity: number;
  deadline?: string | null;
}
