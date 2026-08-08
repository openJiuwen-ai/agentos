/**
 * CronHomePage — 定时任务主页面(Phase 2 屏幕重排)。组合 Phase 1 原子件 + Phase 2 组合件,
 * 还原设计稿"空白首页"(无任务)与"首页"(有任务)两屏。
 *
 * 结构:页头(title+subtitle | 黑色"创建"CreateDropdown solid)
 *   → 有任务时显示工具行(SegmentedFilter + SearchBox + ViewToggle)
 *   → TabBar(任务列表 / 执行历史 / 任务模板)→ 按 tab 切换内容。
 * 无任务且 filter=all → 任务列表 tab 渲染 TaskTemplateSection(空白首页"从这里开始");
 * 有任务但 filter/search 无命中 → CronEmptyState。
 * 执行历史 tab(Phase 4)→ CronHistoryList 真实会话列表(projectId + onOpenSession 由父级注入)。
 *
 * 文案严格取设计稿原文(中文,与原版 1:1)。刻意不用 i18n:i18next 跟随浏览器语言,
 * 英文环境下整页变英文;且 i18n 现存副标题/部分键与设计稿不一致 —— 故按设计稿硬编码。
 *
 * 数据层不动:jobs/filter/search/viewMode/templates 走 cronStore;toggle/run_now/delete
 * 与"手动创建"经回调上抛(由 CronPanel wrapper 走既有 RPC + 弹窗)。
 * 卡片 description / 下次执行:SidebarCronJob 列表无 description,按 job 异步 getJob + previewJob 注入。
 */
import { useEffect, useMemo, useState } from 'react';
import type { CronTemplateUI, FilterKind } from '../../types';
import { useCronStore } from '../../stores';
import { SegmentedFilter } from './SegmentedFilter';
import { SearchBox } from './SearchBox';
import { ViewToggle } from './ViewToggle';
import { TabBar } from './TabBar';
import { CreateDropdown } from './CreateDropdown';
import { CronCard } from './CronCard';
import { TaskTemplateSection } from './TaskTemplateSection';
import { CronEmptyState } from './CronEmptyState';
import { CronHistoryList } from './CronHistoryList';
import cronEmptyUrl from '../../assets/cron/empty-bird.svg';

type CronTab = 'list' | 'history' | 'template';

interface JobDetail {
  description?: string;
  nextRunAt?: number | string | null;
}

export interface CronHomePageProps {
  onToggle: (id: string) => void;
  onRunNow: (id: string) => void;
  onDelete: (id: string) => void;
  /** Phase 3:编辑(开抽屉 edit 模式) */
  onEdit: (id: string) => void;
  /** "手动创建" —— 打开抽屉 create 模式 */
  onCreateManual: () => void;
  /** Phase 3:模板"使用" —— 开抽屉 template 模式预填 */
  onUseTemplate: (template: CronTemplateUI) => void;
  /** "通过聊天创建" —— Phase 2 占位 */
  onCreateViaChat: () => void;
  /** Phase 4:当前项目 id(执行历史数据范围) */
  projectId: string;
  /** Phase 4:点击执行历史某条 → 打开会话(切到对话视图) */
  onOpenSession: (sessionId: string) => void;
  /** Phase 3:创建完成态高亮的 job id(2s 闪后由父级清除) */
  highlightId?: string | null;
}

/** 文案严格对齐设计稿"定时任务 - {空白首页,首页}"原文(中文)。 */
const TEXT = {
  title: '定时任务',
  subtitle: '设置任务执行时间，智能体将在指定时间自动运行并生成结果',
  createTrigger: '创建',
  createManual: '手动创建',
  createViaChat: '通过聊天创建',
  createJobFull: '创建定时任务',
  searchPlaceholder: '请输入搜索内容',
  filterAll: '全部任务',
  filterRunning: '运行中',
  filterPaused: '已暂停',
  tabList: '任务列表',
  tabHistory: '执行历史',
  tabTemplate: '任务模板',
} as const;

export function CronHomePage({
  onToggle,
  onRunNow,
  onDelete,
  onEdit,
  onCreateManual,
  onUseTemplate,
  onCreateViaChat,
  projectId,
  onOpenSession,
  highlightId,
}: CronHomePageProps) {
  const jobs = useCronStore(s => s.jobs);
  const filter = useCronStore(s => s.filter);
  const searchKeyword = useCronStore(s => s.searchKeyword);
  const viewMode = useCronStore(s => s.viewMode);
  const templates = useCronStore(s => s.templates);
  const setFilter = useCronStore(s => s.setFilter);
  const setSearchKeyword = useCronStore(s => s.setSearchKeyword);
  const setViewMode = useCronStore(s => s.setViewMode);
  const getJob = useCronStore(s => s.getJob);
  const previewJob = useCronStore(s => s.previewJob);

  const [tab, setTab] = useState<CronTab>('list');
  const [details, setDetails] = useState<Record<string, JobDetail>>({});

  // 按 job 异步取 description(getJob)+ 下次执行(previewJob),注入对应 CronCard。
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const entries = await Promise.all(
        jobs.map(async (j): Promise<[string, JobDetail]> => {
          const [full, next] = await Promise.all([
            getJob(j.id).catch(() => null),
            j.enabled && !j.expired ? previewJob(j.id, 1).catch(() => []) : Promise.resolve([]),
          ]);
          const first = next[0];
          return [j.id, { description: full?.description ?? '', nextRunAt: first?.push_at ?? first?.wake_at ?? null }];
        })
      );
      if (!cancelled) setDetails(Object.fromEntries(entries));
    })();
    return () => {
      cancelled = true;
    };
  }, [jobs, getJob, previewJob]);

  const filteredJobs = useMemo(() => {
    const kw = searchKeyword.trim().toLowerCase();
    return jobs.filter(j => {
      if (filter === 'running' && !j.enabled) return false;
      if (filter === 'paused' && j.enabled) return false;
      if (kw && !j.name.toLowerCase().includes(kw)) return false;
      return true;
    });
  }, [jobs, filter, searchKeyword]);

  const hasJobs = jobs.length > 0;
  const isListEmpty = filteredJobs.length === 0;

  const createItems = [
    { key: 'manual', label: TEXT.createManual },
    { key: 'viaChat', label: TEXT.createViaChat },
  ];
  const handleCreateSelect = (key: string) => {
    if (key === 'manual') onCreateManual();
    else if (key === 'viaChat') onCreateViaChat();
  };

  const filterOptions: { value: FilterKind; label: string }[] = [
    { value: 'all', label: TEXT.filterAll },
    { value: 'running', label: TEXT.filterRunning },
    { value: 'paused', label: TEXT.filterPaused },
  ];

  const tabOptions: readonly { value: CronTab; label: string }[] = [
    { value: 'list', label: TEXT.tabList },
    { value: 'history', label: TEXT.tabHistory },
    { value: 'template', label: TEXT.tabTemplate },
  ];

  const handleUseTemplate = (template: CronTemplateUI) => {
    // Phase 3:模板"使用" → 开抽屉 template 模式(name/prompt/cronExpr 预填)。
    onUseTemplate(template);
  };

  return (
    <div className="cron-home">
      <header className="cron-home__header">
        <div className="cron-home__heading">
          <h1 className="cron-home__title">{TEXT.title}</h1>
          <span className="cron-home__subtitle">{TEXT.subtitle}</span>
        </div>
        <CreateDropdown variant="solid" triggerLabel={TEXT.createTrigger} items={createItems} onSelect={handleCreateSelect} />
      </header>

      <TabBar tabs={tabOptions} value={tab} onChange={setTab} />

      {hasJobs ? (
        <div className="cron-home__tools">
          <SegmentedFilter options={filterOptions} value={filter} onChange={setFilter} />
          <div className="cron-home__tools-right">
            <div className="cron-home__search">
              <SearchBox value={searchKeyword} onChange={setSearchKeyword} placeholder={TEXT.searchPlaceholder} />
            </div>
            <ViewToggle value={viewMode} onChange={setViewMode} />
          </div>
        </div>
      ) : null}

      <div className="cron-home__content">
        {tab === 'list' ? (
          isListEmpty ? (
            hasJobs ? (
              <CronEmptyState />
            ) : (
              <>
                <div className="cron-empty-hero">
                  <img className="cron-empty-hero__img" src={cronEmptyUrl} alt="" draggable={false} />
                  <CreateDropdown variant="outline" triggerLabel={TEXT.createJobFull} items={createItems} onSelect={handleCreateSelect} />
                </div>
                <TaskTemplateSection templates={templates} onUse={handleUseTemplate} onMore={() => setTab('template')} />
              </>
            )
          ) : (
            <div className={`cron-job-list${viewMode === 'grid' ? ' cron-job-list--grid' : ''}`}>
              {filteredJobs.map(j => {
                const detail = details[j.id];
                return (
                  <CronCard
                    key={j.id}
                    id={j.id}
                    name={j.name}
                    enabled={j.enabled}
                    expired={j.expired ?? false}
                    cronExpr={j.cron_expr}
                    description={detail?.description}
                    nextRunAt={detail?.nextRunAt}
                    viewMode={viewMode}
                    onToggle={onToggle}
                    onRunNow={onRunNow}
                    onDelete={onDelete}
                    onEdit={onEdit}
                    flash={highlightId === j.id}
                  />
                );
              })}
            </div>
          )
        ) : tab === 'history' ? (
          <CronHistoryList projectId={projectId} onOpenSession={onOpenSession} />
        ) : (
          <TaskTemplateSection templates={templates} onUse={handleUseTemplate} onMore={() => setTab('template')} />
        )}
      </div>
    </div>
  );
}
