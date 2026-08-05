/**
 * Agent 反问用户卡片 —— 按 UI_design/Agent反问用户 设计稿实现
 * 聊天流内展示：头部(请回答问题 + 翻页 + 关闭) / 问题区(复选 + 其他输入) / 底部(取消/跳过/确定)
 */
import { useMemo, useState } from 'react';
import { FileText, ChevronLeft, ChevronRight, X } from 'lucide-react';
import type { AskUserQuestionPayload, UserAnswer } from '../../types';
import './AskUserQuestionCard.css';

interface AskUserQuestionCardProps {
  payload: AskUserQuestionPayload;
  onSubmit: (answers: UserAnswer[]) => void;
  onSkip: () => void;
  onDismiss: () => void;
}

interface QuestionState {
  selected: string[];
  otherChecked: boolean;
  custom: string;
}

export function AskUserQuestionCard({ payload, onSubmit, onSkip, onDismiss }: AskUserQuestionCardProps) {
  const questions = useMemo(() => payload.questions ?? [], [payload.questions]);
  const [index, setIndex] = useState(0);
  const [states, setStates] = useState<Record<number, QuestionState>>({});

  const current = questions[index];
  const currentState: QuestionState = states[index] ?? { selected: [], otherChecked: false, custom: '' };

  const updateState = (patch: Partial<QuestionState>) => {
    setStates((prev) => ({
      ...prev,
      [index]: { ...currentState, ...patch },
    }));
  };

  const toggleOption = (label: string) => {
    const multi = current?.multi_select !== false;
    if (multi) {
      updateState({
        selected: currentState.selected.includes(label)
          ? currentState.selected.filter((item) => item !== label)
          : [...currentState.selected, label],
      });
    } else {
      updateState({ selected: [label] });
    }
  };

  const buildAnswers = (): UserAnswer[] =>
    questions.map((question, i) => {
      const state: QuestionState = states[i] ?? { selected: [], otherChecked: false, custom: '' };
      return {
        question: question.question,
        selected_options: state.selected,
        ...(state.otherChecked && state.custom.trim() ? { custom_input: state.custom.trim() } : {}),
      };
    });

  const handleConfirm = () => onSubmit(buildAnswers());

  if (!current) return null;

  return (
    <div className="askq-card">
      {/* 头部 */}
      <div className="askq-head">
        <div className="askq-head-left">
          <FileText size={13} />
          <span>请回答问题</span>
        </div>
        <div className="askq-head-right">
          {questions.length > 1 ? (
            <span className="askq-pager">
              <button
                className="askq-pager-btn"
                disabled={index === 0}
                onClick={() => setIndex((i) => Math.max(0, i - 1))}
              >
                <ChevronLeft size={13} />
              </button>
              <span className="askq-pager-text">{index + 1}/{questions.length}</span>
              <button
                className="askq-pager-btn"
                disabled={index === questions.length - 1}
                onClick={() => setIndex((i) => Math.min(questions.length - 1, i + 1))}
              >
                <ChevronRight size={13} />
              </button>
            </span>
          ) : null}
          <button className="askq-close" onClick={onDismiss} title="关闭">
            <X size={15} />
          </button>
        </div>
      </div>

      {/* 问题区 */}
      <div className="askq-body">
        {current.header ? <div className="askq-question-header">{current.header}</div> : null}
        <div className="askq-question">{current.question}</div>
        <div className="askq-options">
          {current.options.map((option) => {
            const label = option.label;
            const checked = currentState.selected.includes(label);
            return (
              <label key={label} className="askq-option">
                <span className={`askq-checkbox ${checked ? 'is-checked' : ''}`} onClick={(e) => { e.preventDefault(); toggleOption(label); }}>
                  {checked ? (
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                      <path d="M1.5 5.5L4 8L8.5 2.5" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  ) : null}
                </span>
                <span className="askq-option-label" onClick={(e) => { e.preventDefault(); toggleOption(label); }}>
                  {label}
                  {option.description ? <span className="askq-option-desc">{option.description}</span> : null}
                </span>
              </label>
            );
          })}
          {/* 其他 */}
          <div className="askq-option askq-option--other">
            <span
              className={`askq-checkbox ${currentState.otherChecked ? 'is-checked' : ''}`}
              onClick={() => updateState({ otherChecked: !currentState.otherChecked })}
            >
              {currentState.otherChecked ? (
                <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                  <path d="M1.5 5.5L4 8L8.5 2.5" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              ) : null}
            </span>
            <span className="askq-option-label" onClick={() => updateState({ otherChecked: !currentState.otherChecked })}>其他</span>
          </div>
          {currentState.otherChecked ? (
            <textarea
              className="askq-custom"
              placeholder="请输入补充说明…"
              rows={2}
              value={currentState.custom}
              onChange={(e) => updateState({ custom: e.target.value })}
            />
          ) : null}
        </div>
      </div>

      {/* 底部 */}
      <div className="askq-foot">
        <button className="btn btn-ghost btn-sm" onClick={onDismiss}>取消</button>
        <button className="btn btn-ghost btn-sm" onClick={onSkip}>跳过</button>
        <button className="btn btn-dark btn-sm" onClick={handleConfirm}>确定</button>
      </div>
    </div>
  );
}
