import React, { useState, useRef, useEffect, useCallback } from 'react';
import { MoreVertical } from 'lucide-react';

// --- Types ---

export interface ActionMenuItem {
    type?: 'action'; // default
    label: string;
    icon?: React.ComponentType<{ className?: string }>;
    onClick: () => void;
    /** Render in red to signal destructive actions like Delete */
    variant?: 'danger';
    disabled?: boolean;
    /** Shown in place of label when disabled (e.g. "Deleting…") */
    loadingLabel?: string;
}

export interface ActionMenuDivider {
    type: 'divider';
}

export type ActionMenuEntry = ActionMenuItem | ActionMenuDivider;

interface ActionMenuProps {
    items: ActionMenuEntry[];
}

/**
 * Reusable three-dot (⋮) dropdown menu.
 *
 * Uses position:fixed so the dropdown is never clipped by
 * parent overflow containers (tables, cards, etc.).
 *
 * Opens on click, closes on outside-click or Escape.
 * Keyboard: Tab through items, Enter to activate, Escape to close.
 */
export default function ActionMenu({ items }: ActionMenuProps) {
    const [open, setOpen] = useState(false);
    const triggerRef = useRef<HTMLButtonElement>(null);
    const menuRef = useRef<HTMLDivElement>(null);

    // Position state for the fixed-positioned dropdown
    const [menuPos, setMenuPos] = useState({ top: 0, left: 0 });

    const MENU_WIDTH = 192; // tailwind w-48
    const VIEWPORT_PADDING = 8;
    const MENU_GAP = 4;

    // Recalculate dropdown position from the trigger button's rect
    const updatePosition = useCallback(() => {
        if (!triggerRef.current) return;
        const rect = triggerRef.current.getBoundingClientRect();

        const estimatedMenuHeight = Math.max(120, items.length * 40);
        const menuHeight = menuRef.current?.offsetHeight ?? estimatedMenuHeight;

        const preferredLeft = rect.right - MENU_WIDTH;
        const maxLeft = window.innerWidth - MENU_WIDTH - VIEWPORT_PADDING;
        const left = Math.max(VIEWPORT_PADDING, Math.min(preferredLeft, maxLeft));

        const preferredBelowTop = rect.bottom + MENU_GAP;
        const maxTop = window.innerHeight - menuHeight - VIEWPORT_PADDING;
        const top =
            preferredBelowTop <= maxTop
                ? preferredBelowTop
                : Math.max(VIEWPORT_PADDING, rect.top - menuHeight - MENU_GAP);

        setMenuPos({
            top,
            left,
        });
    }, [items.length]);

    // Close on outside click
    const handleClickOutside = useCallback((e: MouseEvent) => {
        if (
            menuRef.current &&
            !menuRef.current.contains(e.target as Node) &&
            triggerRef.current &&
            !triggerRef.current.contains(e.target as Node)
        ) {
            setOpen(false);
        }
    }, []);

    // Close on Escape and return focus to trigger
    const handleKeyDown = useCallback(
        (e: KeyboardEvent) => {
            if (e.key === 'Escape' && open) {
                setOpen(false);
                triggerRef.current?.focus();
            }
        },
        [open],
    );

    const handleScroll = useCallback(() => {
        setOpen(false);
    }, []);

    useEffect(() => {
        if (open) {
            document.addEventListener('mousedown', handleClickOutside);
            document.addEventListener('keydown', handleKeyDown);
            window.addEventListener('scroll', handleScroll, { capture: true });
            window.addEventListener('resize', updatePosition);
        }
        return () => {
            document.removeEventListener('mousedown', handleClickOutside);
            document.removeEventListener('keydown', handleKeyDown);
            window.removeEventListener('scroll', handleScroll, { capture: true });
            window.removeEventListener('resize', updatePosition);
        };
    }, [open, handleClickOutside, handleKeyDown, handleScroll, updatePosition]);

    // Focus the first menu item when the dropdown opens
    useEffect(() => {
        if (open && menuRef.current) {
            // Measure final height and reposition so the menu never clips at viewport edges.
            updatePosition();
            const firstItem = menuRef.current.querySelector<HTMLButtonElement>(
                '[role="menuitem"]',
            );
            firstItem?.focus();
        }
    }, [open, updatePosition]);

    const toggle = () => {
        if (!open) {
            updatePosition(); // calculate position right before opening
        }
        setOpen((prev) => !prev);
    };

    return (
        <>
            <button
                ref={triggerRef}
                onClick={toggle}
                className="action-menu-trigger"
                aria-haspopup="true"
                aria-expanded={open}
                title="Actions"
            >
                <MoreVertical className="w-5 h-5" />
            </button>

            {open && (
                <div
                    ref={menuRef}
                    role="menu"
                    className="action-menu-dropdown"
                    /* Fixed position keeps the dropdown above all overflow containers */
                    style={{
                        position: 'fixed',
                        top: menuPos.top,
                        left: Math.max(menuPos.left, 8), // never go off-screen left
                        zIndex: 9999,
                    }}
                >
                    {items.map((entry, idx) => {
                        if (entry.type === 'divider') {
                            return <div key={`div-${idx}`} className="action-menu-divider" />;
                        }

                        const item = entry as ActionMenuItem;
                        const Icon = item.icon;
                        const isDanger = item.variant === 'danger';

                        return (
                            <button
                                key={idx}
                                role="menuitem"
                                disabled={item.disabled}
                                className={`action-menu-item ${isDanger ? 'action-menu-item-danger' : ''}`}
                                onClick={() => {
                                    item.onClick();
                                    setOpen(false);
                                }}
                            >
                                {Icon && <Icon className="w-4 h-4 flex-shrink-0" />}
                                <span>
                                    {item.disabled && item.loadingLabel
                                        ? item.loadingLabel
                                        : item.label}
                                </span>
                            </button>
                        );
                    })}
                </div>
            )}
        </>
    );
}
