/**
 * SearchBox — 搜索框(请输入搜索内容)。
 * 1:1 设计稿:灰底胶囊(radius 24,padding 9 12,无描边)+ 16px 搜索图标 + placeholder rgba(0,0,0,.6)/16/400/21。
 * 受控;图标用设计系统内联 SVG(cronSvgIcons.search,currentColor)。
 */
import { useState } from 'react';
import { CronSvgIcon } from './cronSvgIcons';

export interface SearchBoxProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}

export function SearchBox({ value, onChange, placeholder }: SearchBoxProps) {
  const [focus, setFocus] = useState(false);
  const Icon = CronSvgIcon.search;
  return (
    <div className={`cron-search${focus ? ' cron-search--focus' : ''}`}>
      <Icon className="cron-search__icon" aria-hidden />
      <input
        className="cron-search__input"
        type="text"
        value={value}
        placeholder={placeholder}
        onChange={e => onChange(e.target.value)}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
      />
    </div>
  );
}
