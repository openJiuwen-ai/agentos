import type { SVGProps } from 'react';
import ChevronDownSvg from '../../assets/icons/chevron-down.svg?react';
import NewProjectSvg from '../../assets/icons/new-project.svg?react';
import ProjectSpaceSvg from '../../assets/icons/project-space.svg?react';
import SelectProjectPathSvg from '../../assets/icons/select-project-path.svg?react';

type IconProps = SVGProps<SVGSVGElement> & {
  size?: number | string;
};

function withSize(
  Icon: typeof ChevronDownSvg,
  { size = 16, width, height, ...rest }: IconProps,
) {
  return (
    <Icon
      width={width ?? size}
      height={height ?? size}
      {...rest}
    />
  );
}

/** 下拉 — 创建项目-新版/图标/下拉.svg */
export function ProjectChevronDownIcon(props: IconProps) {
  return withSize(ChevronDownSvg, props);
}

/** 新建项目 — 创建项目-新版/图标/新建项目.svg */
export function NewProjectIcon(props: IconProps) {
  return withSize(NewProjectSvg, props);
}

/** 项目空间 — 创建项目-新版/图标/项目空间图标.svg */
export function ProjectSpaceIcon(props: IconProps) {
  return withSize(ProjectSpaceSvg, props);
}

/** 选择项目路径 — 创建项目-新版/图标/选择项目路径.svg */
export function SelectProjectPathIcon(props: IconProps) {
  return withSize(SelectProjectPathSvg, props);
}
