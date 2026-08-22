/* Shared, accessible replacement for browser prompt/confirm dialogs. */
(function(root) {
    function text(value, fallback) {
        return value || fallback;
    }

    function localized(key) {
        return root.EpubBrowserI18n ? root.EpubBrowserI18n.t('dialog.' + key) : key;
    }

    function open(options) {
        return new Promise(function(resolve) {
            var previousFocus = document.activeElement;
            var modal = document.createElement('div');
            var backdrop = document.createElement('div');
            var dialog = document.createElement('section');
            var header = document.createElement('div');
            var title = document.createElement('h2');
            var message = document.createElement('p');
            var footer = document.createElement('div');
            var cancel = document.createElement('button');
            var confirm = document.createElement('button');
            var input = null;

            modal.className = 'app-dialog-modal';
            modal.setAttribute('role', options.destructive ? 'alertdialog' : 'dialog');
            modal.setAttribute('aria-modal', 'true');
            modal.setAttribute('aria-labelledby', 'appDialogTitle');
            backdrop.className = 'app-dialog-backdrop';
            dialog.className = 'app-dialog';
            header.className = 'app-dialog-header';
            title.id = 'appDialogTitle';
            title.textContent = text(options.title, localized('title'));
            message.className = 'app-dialog-message';
            message.textContent = options.message || '';
            footer.className = 'app-dialog-footer';
            cancel.type = 'button';
            cancel.className = 'app-dialog-button app-dialog-cancel';
            cancel.textContent = text(options.cancelText, localized('cancel'));
            confirm.type = 'button';
            confirm.className = 'app-dialog-button app-dialog-confirm' + (options.destructive ? ' app-dialog-destructive' : '');
            confirm.textContent = text(options.confirmText, localized('confirm'));

            header.appendChild(title);
            dialog.appendChild(header);
            if (options.message) dialog.appendChild(message);
            if (options.input) {
                var label = document.createElement('label');
                input = document.createElement('input');
                label.className = 'app-dialog-label';
                label.htmlFor = 'appDialogInput';
                label.textContent = text(options.inputLabel, text(options.title, localized('value')));
                input.id = 'appDialogInput';
                input.className = 'app-dialog-input';
                input.type = options.inputType || 'text';
                input.value = options.defaultValue || '';
                input.autocomplete = 'off';
                dialog.appendChild(label);
                dialog.appendChild(input);
            }
            footer.appendChild(cancel);
            footer.appendChild(confirm);
            dialog.appendChild(footer);
            modal.appendChild(backdrop);
            modal.appendChild(dialog);
            document.body.appendChild(modal);

            function close(result) {
                document.removeEventListener('keydown', onKeydown);
                modal.remove();
                if (previousFocus && typeof previousFocus.focus === 'function') previousFocus.focus();
                resolve(result);
            }

            function submit() {
                close(input ? input.value : true);
            }

            function onKeydown(event) {
                if (event.key === 'Escape') {
                    event.preventDefault();
                    close(options.input ? null : false);
                } else if (event.key === 'Enter' && input && document.activeElement === input) {
                    event.preventDefault();
                    submit();
                } else if (event.key === 'Tab') {
                    var focusable = [cancel, confirm];
                    if (input) focusable.unshift(input);
                    var index = focusable.indexOf(document.activeElement);
                    if (event.shiftKey && index <= 0) {
                        event.preventDefault();
                        focusable[focusable.length - 1].focus();
                    } else if (!event.shiftKey && index === focusable.length - 1) {
                        event.preventDefault();
                        focusable[0].focus();
                    }
                }
            }

            cancel.addEventListener('click', function() { close(options.input ? null : false); });
            confirm.addEventListener('click', submit);
            backdrop.addEventListener('click', function() { close(options.input ? null : false); });
            document.addEventListener('keydown', onKeydown);
            (input || confirm).focus();
            if (input && options.selectOnOpen) input.select();
        });
    }

    root.EpubDialog = {
        confirm: function(options) {
            return open(options || {});
        },
        prompt: function(options) {
            options = options || {};
            options.input = true;
            return open(options);
        }
    };
})(typeof window !== 'undefined' ? window : globalThis);
