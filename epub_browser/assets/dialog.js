/* Shared, accessible replacement for browser prompt/confirm dialogs. */
(function(root) {
    function text(value, fallback) {
        return value || fallback;
    }

    function localized(key) {
        return root.EpubBrowserI18n ? root.EpubBrowserI18n.t('dialog.' + key) : key;
    }

    var layers = [];
    var serial = 0;

    function bind(node, key, value, params) {
        if (key) {
            node.setAttribute('data-i18n', key);
            if (params) node.setAttribute('data-i18n-params', JSON.stringify(params));
            node.textContent = root.EpubBrowserI18n ? root.EpubBrowserI18n.t(key, params) : value || key;
        } else {
            node.textContent = value || '';
        }
    }

    function createShell(options) {
        var modal = document.createElement('div');
        var backdrop = document.createElement('div');
        var dialog = document.createElement('section');
        var header = document.createElement('div');
        var title = document.createElement('h2');
        title.id = 'appDialogTitle' + (++serial);
        if (options.titleDirection) title.dir = options.titleDirection;
        bind(title, options.titleKey, text(options.title, localized('title')));
        modal.className = 'app-dialog-modal';
        modal.setAttribute('role', options.destructive ? 'alertdialog' : 'dialog');
        modal.setAttribute('aria-modal', 'true');
        modal.setAttribute('aria-labelledby', title.id);
        modal.tabIndex = -1;
        backdrop.className = 'app-dialog-backdrop';
        dialog.className = 'app-dialog';
        header.className = 'app-dialog-header';
        header.appendChild(title);
        dialog.appendChild(header);
        modal.appendChild(backdrop);
        modal.appendChild(dialog);
        return { modal: modal, backdrop: backdrop, dialog: dialog, header: header };
    }

    function mount(shell, options) {
        var modal = shell.modal;
        var previousFocus = document.activeElement;
        function onKeydown(event) {
            if (layers[layers.length - 1] !== modal) return;
            if (event.key === 'Escape') {
                event.preventDefault();
                event.stopImmediatePropagation();
                options.dismiss();
            } else if (event.key === 'Tab') {
                var focusable = Array.from(modal.querySelectorAll(
                    'a[href], button:not(:disabled), input:not(:disabled), select:not(:disabled), textarea:not(:disabled), [tabindex="0"]'
                )).filter(function(node) { return node.tabIndex >= 0 && node.getClientRects().length; });
                var index = focusable.indexOf(document.activeElement);
                if (index < 0 || (event.shiftKey ? index === 0 : index === focusable.length - 1)) {
                    event.preventDefault();
                    (focusable[event.shiftKey ? focusable.length - 1 : 0] || modal).focus();
                }
            } else if (options.keydown) {
                options.keydown(event);
            }
        }
        var underlying = layers[layers.length - 1];
        if (underlying) underlying.inert = true;
        layers.push(modal);
        document.body.appendChild(modal);
        shell.backdrop.addEventListener('click', options.dismiss);
        document.addEventListener('keydown', onKeydown, true);
        (options.initialFocus || modal).focus();
        return {
            remove: function() {
                modal.remove();
                layers.splice(layers.indexOf(modal), 1);
                var top = layers[layers.length - 1];
                if (top) top.inert = false;
                document.removeEventListener('keydown', onKeydown, true);
                setTimeout(function() {
                    // A caller may already have opened another dialog.
                    if (layers[layers.length - 1] !== top) return;
                    var target = typeof options.returnFocus === 'function'
                        ? options.returnFocus() : options.returnFocus || previousFocus;
                    if (target && typeof target.focus === 'function') target.focus();
                }, 0);
            }
        };
    }

    function panel(options) {
        var shell = createShell(options);
        shell.dialog.className += ' app-dialog-panel';
        if (options.fullscreen) shell.modal.className += ' app-dialog-fullscreen';
        var body = document.createElement('div');
        body.className = 'app-dialog-body';
        shell.dialog.appendChild(body);
        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'app-dialog-button app-dialog-close';
        var closeKey = options.closeTextKey || (options.closeText ? null : 'dialog.close');
        if (closeKey) close.setAttribute('data-i18n-aria-label', closeKey);
        close.setAttribute('aria-label', closeKey && root.EpubBrowserI18n
            ? root.EpubBrowserI18n.t(closeKey) : options.closeText || closeKey);
        var icon = document.createElement('i');
        icon.className = 'fas fa-times';
        icon.setAttribute('aria-hidden', 'true');
        close.appendChild(icon);
        shell.header.appendChild(close);
        function dismiss() {
            if (close.disabled) return;
            layer.remove();
            if (options.onClose) options.onClose();
        }
        close.addEventListener('click', dismiss);
        var layer = mount(shell, {
            initialFocus: close, returnFocus: options.returnFocus, dismiss: dismiss
        });
        return { modal: shell.modal, body: body, closeButton: close };
    }

    function open(options) {
        return new Promise(function(resolve) {
            var previousFocus = document.activeElement;
            var shell = createShell(options);
            var modal = shell.modal;
            var dialog = shell.dialog;
            var message = document.createElement('p');
            var details = null;
            var footer = document.createElement('div');
            var cancel = document.createElement('button');
            var confirm = document.createElement('button');
            var input = null;
            var pending = false, closed = false;
            message.className = 'app-dialog-message';
            message.id = 'appDialogMessage';
            bind(message,options.messageKey,options.message,options.messageParams);
            footer.className = 'app-dialog-footer';
            cancel.type = 'button';
            cancel.className = 'app-dialog-button app-dialog-cancel';
            bind(cancel,options.cancelTextKey,text(options.cancelText,localized('cancel')));
            confirm.type = 'button';
            confirm.className = 'app-dialog-button app-dialog-confirm' + (options.destructive ? ' app-dialog-destructive' : '');
            bind(confirm,options.confirmTextKey,text(options.confirmText,localized('confirm')));

            if (options.message || options.messageKey) {
                dialog.appendChild(message);
                modal.setAttribute('aria-describedby', message.id);
            }
            if (Array.isArray(options.details) && options.details.length) {
                details = document.createElement('ul');
                details.className = 'app-dialog-details';
                details.id = 'appDialogDetails';
                options.details.forEach(function(value) {
                    var item = document.createElement('li');
                    item.textContent = String(value);
                    details.appendChild(item);
                });
                dialog.appendChild(details);
                modal.setAttribute(
                    'aria-describedby',
                    (options.message || options.messageKey ? message.id + ' ' : '') + details.id
                );
            }
            if (options.input) {
                var label = document.createElement('label');
                input = document.createElement('input');
                label.className = 'app-dialog-label';
                label.htmlFor = 'appDialogInput';
                bind(label,options.inputLabelKey,text(options.inputLabel,text(options.title,localized('value'))));
                input.id = 'appDialogInput';
                input.className = 'app-dialog-input';
                input.type = options.inputType || 'text';
                input.value = options.defaultValue || '';
                input.autocomplete = 'off';
                if(options.maxLength)input.maxLength=options.maxLength;
                dialog.appendChild(label);
                dialog.appendChild(input);
                if(options.inputHelp || options.inputHelpKey) {
                    var help=document.createElement('p');help.id='appDialogHelp';help.className='app-dialog-help';
                    bind(help,options.inputHelpKey,options.inputHelp);
                    input.setAttribute('aria-describedby',help.id);dialog.appendChild(help);
                }
                if (options.expectedValue !== undefined) {
                    confirm.disabled = input.value !== String(options.expectedValue);
                    input.addEventListener('input', function() {
                        confirm.disabled = input.value !== String(options.expectedValue);
                    });
                }
            }
            var error=document.createElement('p');error.className='app-dialog-error';error.id='appDialogError';
            error.hidden=true;error.setAttribute('role','alert');dialog.appendChild(error);
            footer.appendChild(cancel);
            footer.appendChild(confirm);
            dialog.appendChild(footer);

            function close(result) {
                if(pending || closed)return;closed=true;
                resolve(result);
                layer.remove();
            }

            function submit() {
                if (confirm.disabled) return;
                if(typeof options.onSubmit!=='function') {close(input ? input.value : true);return;}
                var value=input ? input.value : true;
                pending=true;confirm.disabled=true;cancel.disabled=true;error.hidden=true;
                if(input)input.disabled=true;
                modal.setAttribute('aria-busy','true');
                Promise.resolve().then(function(){return options.onSubmit(value);}).then(function(){
                    pending=false;close(value);
                }).catch(function(){
                    pending=false;confirm.disabled=false;cancel.disabled=false;error.hidden=false;
                    if(input)input.disabled=false;
                    modal.setAttribute('aria-busy','false');
                    bind(error,options.errorKey,options.errorText || localized('error'));
                    if(input){input.setAttribute('aria-describedby','appDialogError'+(options.inputHelpKey || options.inputHelp?' appDialogHelp':''));input.focus();}
                });
            }

            cancel.addEventListener('click', function() { close(options.input ? null : false); });
            confirm.addEventListener('click', submit);
            var layer = mount(shell, {
                returnFocus: options.returnFocus || previousFocus,
                dismiss: function() { close(options.input ? null : false); },
                keydown: function(event) {
                    if (event.key === 'Enter' && input && document.activeElement === input) {
                        event.preventDefault();
                        submit();
                    }
                },
                initialFocus: input || (options.destructive ? cancel : confirm)
            });
            if (input && options.selectOnOpen) input.select();
        });
    }

    root.EpubDialog = {
        panel: panel,
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
