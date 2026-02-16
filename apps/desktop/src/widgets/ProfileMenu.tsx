import { HelpCircle, Info, Settings, UserCircle } from "lucide-react";
import type { AppPage } from "../shared/types/ui";
import DropdownMenu from "../shared/ui/DropdownMenu";

export type ProfileMenuProps = {
  onNavigate?: (page: AppPage) => void;
};

export default function ProfileMenu({ onNavigate }: ProfileMenuProps) {
  return (
    <DropdownMenu
      align="left"
      side="top"
      width={220}
      items={[
        {
          id: "settings",
          label: "Настройки",
          icon: <Settings size={16} />,
          onSelect: () => onNavigate?.("settings")
        },
        { id: "help", label: "Справка", icon: <HelpCircle size={16} /> },
        { id: "about", label: "О программе", icon: <Info size={16} /> }
      ]}
      trigger={({ open, toggle }) => (
        <button className="profile-button" type="button" onClick={toggle} aria-expanded={open}>
          <span className="profile-button-title">
            <UserCircle size={18} />
            <span>Профиль</span>
          </span>
          <span className="profile-button-meta">{open ? "▴" : "▾"}</span>
        </button>
      )}
    />
  );
}
