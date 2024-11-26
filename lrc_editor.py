#!/usr/bin/env python3
import dbus
import curses
import time
import logging
from pathlib import Path
from urllib.parse import unquote
from dbus.mainloop.glib import DBusGMainLoop
import threading
import gi
gi.require_version('GLib', '2.0')
from gi.repository import GLib

"""

This script is a Python-based LRC (Lyric) Editor integrated with MPRIS 
(Media Player Remote Interfacing Specification). It allows users to create or edit 
synchronized lyrics files (.lrc) while listening to audio tracks in a media player 
that supports the MPRIS interface, such as VLC, Rhythmbox, or Audacious. 
The script uses a curses-based text interface to provide a simple terminal-based UI for managing lyrics.

"""

class LRCEditor:
    def __init__(self):
        # Initialize DBus main loop
        DBusGMainLoop(set_as_default=True)
        self.bus = dbus.SessionBus()
        self.lines = []
        self.current_line = 0
        self.modified = False
        self.last_timestamp = None
        self.last_timestamp_value = None  # Store the actual seconds value
        self.last_timestamp_time = None   # Store when the timestamp was added
        self.current_song = "No song playing"
        self.current_file = None
        self.current_player = None
        self.player_interface = None
        self.properties_interface = None
        self.edit_mode = False  # Default to edit mode
        self.sync_ticker = None
        self.debug_mode = False  # Flag to toggle detailed logging
        # self.debug_mode = True  # Flag to toggle detailed logging
        self.sync_lock = threading.Lock()
        
        # Initialize GLib main loop
        self.loop = GLib.MainLoop()
        self.loop_thread = threading.Thread(target=self.loop.run)
        self.loop_thread.daemon = True
        self.loop_thread.start()
        
        if self.debug_mode:
            self.setup_logging()        
        # Set up signal handler for property changes
        self.bus.add_signal_receiver(
            self._properties_changed,
            dbus_interface="org.freedesktop.DBus.Properties",
            signal_name="PropertiesChanged",
            path="/org/mpris/MediaPlayer2"
        )

    def setup_logging(self):
        """Configure logging only if debug_mode is enabled."""
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(levelname)s - %(message)s',
            filename='mpris_debug.log'
        )
        logging.debug("Logging initialized.")

    def debug_log(self, message):
        """Log messages only when debug_mode is enabled."""
        if self.debug_mode:
            logging.debug(message)

    # Example usage of the debug_log method:
    def _update_metadata(self):
        """Update metadata from player."""
        try:
            # Existing logic
            if self.debug_mode:
                self.debug_log(f"Updated metadata: {metadata}")
        except Exception as e:
            self.debug_log(f"Error updating metadata: {str(e)}")

    def cleanup(self):
        """Clean up resources safely"""
        try:
            if hasattr(self, 'loop') and self.loop.is_running():
                self.loop.quit()
                if hasattr(self, 'loop_thread'):
                    self.loop_thread.join(timeout=1.0)
        except:
            pass  # Ignore cleanup errors during shutdown

    def __del__(self):
        """Clean up resources"""
        self.cleanup()

    def _properties_changed(self, interface, changed_props, invalidated_props):
        """Handle property changes from the player"""
        if self.debug_mode:
            logging.debug(f"Properties changed on {interface}: {changed_props}")
        if interface == 'org.mpris.MediaPlayer2.Player':
            if 'PlaybackStatus' in changed_props:
                status = str(changed_props['PlaybackStatus'])
                if self.debug_mode:
                    logging.debug(f"Playback status changed to: {status}")
                if status == 'Playing':
                    # Refresh metadata when playback starts
                    self._update_metadata()

    def _update_metadata(self):
        """Update metadata from player"""
        try:
            if not self.properties_interface:
                return
            metadata = self.properties_interface.Get('org.mpris.MediaPlayer2.Player', 'Metadata')
            if self.debug_mode:
                logging.debug(f"Updated metadata: {metadata}")
            if 'xesam:title' in metadata:
                self.current_song = str(metadata['xesam:title'])
                if 'xesam:artist' in metadata:
                    artists = metadata['xesam:artist']
                    if artists:
                        self.current_song = f"{self.current_song} - {artists[0]}"
                if self.debug_mode:
                    logging.debug(f"Updated current song: {self.current_song}")
            
            # Update current file path
            if 'xesam:url' in metadata:
                url = str(metadata['xesam:url'])
                if url.startswith('file://'):
                    self.current_file = unquote(url[7:])  # Remove 'file://' and decode URL
                    if self.debug_mode:
                        logging.debug(f"Updated current file: {self.current_file}")
        except Exception as e:
            logging.error(f"Error updating metadata: {str(e)}")

    def get_playback_status(self):
        """Get current playback status"""
        try:
            if not self.properties_interface:
                return 'Stopped'
            status = self.properties_interface.Get('org.mpris.MediaPlayer2.Player', 'PlaybackStatus')
            if self.debug_mode:
                logging.debug(f"Current playback status: {status}")
            return str(status)
        except Exception as e:
            logging.error(f"Error getting playback status: {str(e)}")
            return 'Unknown'

    def connect_player(self):
        """Connect to the first available MPRIS player"""
        try:
            if self.debug_mode:
                logging.debug("Attempting to connect to MPRIS player...")
            obj = self.bus.get_object('org.freedesktop.DBus', '/org/freedesktop/DBus')
            dbus_interface = dbus.Interface(obj, 'org.freedesktop.DBus')
            
            services = dbus_interface.ListNames()
            players = [service for service in services if service.startswith('org.mpris.MediaPlayer2.')]
            if self.debug_mode:
                logging.debug(f"Found MPRIS players: {players}")
            
            if not players:
                logging.warning("No MPRIS players found")
                return False

            # Prefer known media players over browser instances
            preferred_players = ['org.mpris.MediaPlayer2.audacious', 'org.mpris.MediaPlayer2.vlc', 
                               'org.mpris.MediaPlayer2.rhythmbox']
            
            # Try to find a preferred player first
            player_name = None
            for preferred in preferred_players:
                if any(p.startswith(preferred) for p in players):
                    player_name = next(p for p in players if p.startswith(preferred))
                    if self.debug_mode:
                        logging.debug(f"Found preferred player: {player_name}")
                    break
            
            # If no preferred player found, use the first available
            if not player_name:
                player_name = players[0]
                if self.debug_mode:
                    logging.debug(f"No preferred player found, using: {player_name}")
                
            if self.debug_mode:
                logging.debug(f"Connecting to player: {player_name}")
            self.current_player = self.bus.get_object(player_name, '/org/mpris/MediaPlayer2')
            self.player_interface = dbus.Interface(self.current_player, 'org.mpris.MediaPlayer2.Player')
            self.properties_interface = dbus.Interface(self.current_player, 'org.freedesktop.DBus.Properties')
            
            # Get initial playback status
            status = self.get_playback_status()
            if self.debug_mode:
                logging.debug(f"Initial playback status: {status}")
            
            if status == 'Playing':
                self._update_metadata()
            
            if self.debug_mode:
                logging.debug("Successfully connected to MPRIS player")
            return True
        except Exception as e:
            logging.error(f"Error connecting to MPRIS player: {str(e)}")
            self.current_player = None
            self.player_interface = None
            self.properties_interface = None
            self.edit_mode = True  # Default to edit mode
            self.sync_ticker = None
            return False

    def get_player_position(self):
        """Get current playback position from active MPRIS player"""
        try:
            if self.current_player is None and not self.connect_player():
                if self.debug_mode:
                    logging.warning("No active MPRIS player connection")
                return -1
                
            status = self.get_playback_status()
            if status != 'Playing':
                if self.debug_mode:
                    logging.debug(f"Player is not playing (status: {status})")
                return -1

            # Get position in microseconds and convert to seconds
            position = self.properties_interface.Get('org.mpris.MediaPlayer2.Player', 'Position') / 1000000
            if self.debug_mode:
                logging.debug(f"Current position: {position:.3f}s")
            
            # Update metadata if we haven't got it yet
            metadata = self.properties_interface.Get('org.mpris.MediaPlayer2.Player', 'Metadata')
            if not self.current_song or self.current_song == "No song playing":
                self._update_metadata()
            
            return position
        except Exception as e:
            if self.debug_mode:
                logging.error(f"Error getting player position: {str(e)}")
            return -1

    def format_timestamp(self, seconds):
        """Convert seconds to LRC timestamp format [mm:ss.xx]"""
        minutes = int(seconds // 60)
        seconds = seconds % 60
        return f"[{minutes:02d}:{seconds:05.2f}]"

    def add_timestamp(self):
        """Add timestamp to current line and move to next line"""
        position = self.get_player_position()
        if position is not None:
            timestamp = self.format_timestamp(position)
            self.last_timestamp = timestamp
            self.last_timestamp_value = position
            self.last_timestamp_time = time.time()
            if self.lines[self.current_line].startswith('['):
                # Replace existing timestamp
                self.lines[self.current_line] = timestamp + self.lines[self.current_line].split(']', 1)[1]
            else:
                # Add new timestamp
                self.lines[self.current_line] = timestamp + self.lines[self.current_line]
            self.modified = True
            # Move to next line if possible
            if self.current_line < len(self.lines) - 1:
                self.current_line += 1
            # If we're at the last line, add a new empty line
            else:
                self.lines.append('')
                self.current_line += 1
            return True
        return False

    def remove_timestamp(self):
        """Remove timestamp from current line or remove empty line"""
        if not self.lines[self.current_line]:  # Empty line
            if len(self.lines) > 1:  # Don't remove if it's the only line
                self.lines.pop(self.current_line)
                if self.current_line >= len(self.lines):
                    self.current_line = len(self.lines) - 1
                self.modified = True
        elif self.lines[self.current_line].startswith('['):
            # Remove timestamp by taking everything after the first ']'
            parts = self.lines[self.current_line].split(']', 1)
            if len(parts) > 1:
                self.lines[self.current_line] = parts[1]
            else:
                self.lines[self.current_line] = ''
            self.modified = True

    def seek_relative(self, offset_seconds):
        """Seek relative to current position by offset_seconds"""
        try:
            if self.player_interface is None and not self.connect_player():
                return False
            
            # Get current position in microseconds
            properties = dbus.Interface(self.current_player, 'org.freedesktop.DBus.Properties')
            position = properties.Get('org.mpris.MediaPlayer2.Player', 'Position')
            
            # Calculate new position (ensure we don't go below 0)
            new_position = max(0, position + (offset_seconds * 1000000))
            
            # Seek to new position
            self.player_interface.Seek(dbus.Int64(new_position - position))
            return True
        except Exception as e:
            return False

    def restart_playback(self):
        """Restart the current track from the beginning"""
        try:
            if self.player_interface is None and not self.connect_player():
                return False
            
            # First seek to start
            self.player_interface.Seek(0)
            # Then ensure playing
            self.player_interface.Play()
            return True
        except Exception as e:
            return False

    def load_lrc_from_current(self):
        """Load LRC file based on current playing file"""
        if not self.current_file:
            logging.warning("No current file playing")
            return False
            
        try:
            # Get the audio file path and try to find matching LRC
            audio_path = Path(self.current_file)
            lrc_path = audio_path.with_suffix('.lrc')
            
            if self.debug_mode:
                logging.debug(f"Trying to load LRC from: {lrc_path}")
            
            if lrc_path.exists():
                self.lines = []
                with open(lrc_path, 'r', encoding='utf-8') as f:
                    self.lines = f.readlines()
                self.current_line = 0
                if self.debug_mode:
                    logging.debug(f"Successfully loaded LRC file: {lrc_path}")
                return True
            else:
                logging.warning(f"No LRC file found at: {lrc_path}")
                # Create empty LRC file
                self.lines = []
                self.current_line = 0
                return True
        except Exception as e:
            logging.error(f"Error loading LRC file: {str(e)}")
            return False

    def get_relative_time(self):
        """Get time relative to last timestamp"""
        if self.last_timestamp_value is None or self.last_timestamp_time is None:
            return None
        
        elapsed = time.time() - self.last_timestamp_time
        current_time = self.last_timestamp_value + elapsed
        return current_time

    def extract_timestamp(self, line):
        """Extract timestamp in seconds from LRC line, returns -1 if no timestamp"""
        if not line.startswith('['):
            return -1
        try:
            timestamp = line[1:line.index(']')]
            minutes, seconds = timestamp.split(':')
            return float(minutes) * 60 + float(seconds)
        except (ValueError, IndexError):
            return -1

    def move_to_closest_timestamp(self):
        """Move to the line with timestamp closest to current playback position"""
        position = self.get_player_position()
        if position < 0:
            return

        closest_diff = float('inf')
        closest_line = self.current_line

        for i, line in enumerate(self.lines):
            timestamp = self.extract_timestamp(line)
            if timestamp >= 0:
                diff = abs(timestamp - position)
                if diff < closest_diff:
                    closest_diff = diff
                    closest_line = i

        if closest_line != self.current_line:
            if self.debug_mode:
                logging.info(f"Moving from line {self.current_line} to {closest_line} (diff: {closest_diff:.3f}s)")
            self.current_line = closest_line
            return True
        return False

    def try_sync_position(self):
        """Try to sync current position with lyrics, returns True if sync succeeded"""
        position = self.get_player_position()
        if position < 0:
            if self.debug_mode:
                logging.debug("Skipping sync: invalid position")
            return False

        current_time = time.time()
        if self.debug_mode:
            logging.info(f"Sync at {current_time:.3f}, position: {position:.3f}s")
        
        # Check if we have any timestamps to sync with
        has_timestamps = any(self.extract_timestamp(line) >= 0 for line in self.lines)
        if not has_timestamps:
            if self.debug_mode:
                logging.debug("No timestamps found in lyrics")
            return False
            
        return self.move_to_closest_timestamp()

    def run(self, stdscr):
        """Main editor loop"""
        try:
            curses.use_default_colors()
            curses.init_pair(1, curses.COLOR_GREEN, -1)
            curses.init_pair(2, curses.COLOR_YELLOW, -1)
            curses.init_pair(3, curses.COLOR_CYAN, -1)  # For relative time
            
            # Set up sync timer
            last_sync_time = 0
            sync_interval = 1.0  # Sync every second
            
            while True:
                # Clear screen
                stdscr.clear()
                
                # Get terminal dimensions
                max_y, max_x = stdscr.getmaxyx()
                
                # Display header with last timestamp and song name
                header = f"LRC Editor [{self.edit_mode and 'Edit Mode' or 'Sync Mode'}] - {self.current_song} - Space: add timestamp, x: remove, r: restart, ←/→: seek ±5s, s: save, l: load LRC, e: toggle mode, q: quit"
                try:
                    stdscr.addstr(0, 0, header[:max_x-1], curses.A_REVERSE)
                except curses.error:
                    pass
                
                # Display lines
                visible_lines = max_y - 4  # Reserve space for header and status
                start_line = max(0, self.current_line - visible_lines + 1)
                for i, line in enumerate(self.lines[start_line:start_line + visible_lines], start=start_line):
                    try:
                        if i == self.current_line:
                            stdscr.addstr(i - start_line + 2, 0, "> " + line[:max_x-3], curses.color_pair(1))
                        else:
                            stdscr.addstr(i - start_line + 2, 0, "  " + line[:max_x-3])
                    except curses.error:
                        break
                
                # Display player position and relative time
                position = self.get_player_position()
                relative_time = self.get_relative_time()
                
                if position is not None or relative_time is not None:
                    status_line = ""
                    if position is not None:
                        status_line += f"Player: {self.format_timestamp(position)}"
                    if relative_time is not None:
                        if status_line:
                            status_line += " | "
                        status_line += f"Local: {self.format_timestamp(relative_time)}"
                    try:
                        if max_y > 3:  # Only show status if there's room
                            stdscr.addstr(min(len(self.lines) - start_line + 3, max_y-1), 0, 
                                        status_line[:max_x-1], curses.color_pair(2))
                    except curses.error:
                        pass
                stdscr.refresh()
                
                # Handle input with timeout for sync
                stdscr.timeout(100)  # 100ms timeout
                try:
                    key = stdscr.getch()
                    current_time = time.time()
                    
                    # Check if it's time to sync
                    if not self.edit_mode and current_time - last_sync_time >= sync_interval:
                        self.move_to_closest_timestamp()
                        last_sync_time = current_time
                        
                    if key == -1:  # No key pressed
                        continue
                        
                    if key == ord(' '):  # Space
                        self.add_timestamp()
                    elif key == ord('x'):  # x key
                        self.remove_timestamp()
                    elif key == ord('r'):  # r key to restart
                        self.restart_playback()
                    elif key == curses.KEY_LEFT:  # Left arrow to seek backward
                        self.seek_relative(-5)
                    elif key == curses.KEY_RIGHT:  # Right arrow to seek forward
                        self.seek_relative(5)
                    elif key == ord('j') or key == curses.KEY_DOWN:
                        self.current_line = min(self.current_line + 1, len(self.lines) - 1)
                    elif key == ord('k') or key == curses.KEY_UP:
                        self.current_line = max(self.current_line - 1, 0)
                    elif key == ord('s'):
                        return 'save'
                    elif key == ord('l'):  # Load LRC for current playing file
                        self.load_lrc_from_current()
                    elif key == ord('e'):  # Toggle edit mode
                        self.edit_mode = not self.edit_mode
                        if self.load_lrc_from_current():
                            if self.debug_mode:
                                logging.debug("Loaded LRC file")
                    elif key == ord('q'):
                        return 'quit'
                    elif key == ord('\n') or key == curses.KEY_ENTER:  # Enter key
                        with self.sync_lock:
                            self.move_to_closest_timestamp()
                except KeyboardInterrupt:
                    return 'quit'
        finally:
            self.cleanup()  # Ensure cleanup happens when editor exits



def main():
    import argparse
    parser = argparse.ArgumentParser(description='LRC Editor with MPRIS 2 support')
    parser.add_argument('file', help='LRC file to edit', nargs='?')
    args = parser.parse_args()
 
    # Initialize editor first to get current song info
    editor = LRCEditor()
    editor.get_player_position()  # Update current song and file info
 
    # If no file specified, try to use the current playing file
    if args.file is None and editor.current_file:
        lrc_path = Path(editor.current_file).with_suffix('.lrc')
    else:
        lrc_path = Path(args.file if args.file else '/tmp/untitled.lrc')
    
    # Create file if it doesn't exist
    if not lrc_path.exists():
        lrc_path.touch()
    
    # Read existing content
    with open(lrc_path, 'r', encoding='utf-8') as f:
        content = f.read().splitlines()
    
    # Initialize editor content
    editor.lines = content if content else ['']
    
    # Run editor
    result = curses.wrapper(editor.run)
    
    # Save if requested
    if result == 'save' and editor.modified:
        with open(lrc_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(editor.lines))
        print(f"Saved changes to {lrc_path}")

if __name__ == '__main__':
    main()
