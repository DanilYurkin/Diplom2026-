// cart.js

// === Функции для работы с корзиной через API ===

async function getCart() {
    try {
        const response = await fetch('/api/cart');
        if (!response.ok) throw new Error('Ошибка при получении корзины');
        return await response.json();
    } catch (error) {
        console.error('Ошибка:', error);
        return { btc: {}, btb: {} };
    }
}

async function removeCartItem(category, productId) {
    try {
        const response = await fetch('/api/cart/remove', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category: category, product_id: productId })
        });
        if (response.ok) {
            location.reload();
        } else {
            alert('Ошибка при удалении товара');
        }
    } catch (error) {
        console.error('Ошибка:', error);
        alert('Не удалось удалить товар');
    }
}

async function updateCartItem(category, productId, quantity) {
    if (quantity < 1) {
        removeCartItem(category, productId);
        return;
    }
    try {
        const response = await fetch('/api/cart/update', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ category: category, product_id: productId, quantity: quantity })
        });
        if (response.ok) {
            location.reload();
        } else {
            alert('Ошибка при обновлении количества');
        }
    } catch (error) {
        console.error('Ошибка:', error);
        alert('Не удалось обновить количество');
    }
}

// === Проверка авторизации ===
async function isUserLoggedIn() {
    try {
        const response = await fetch('/api/auth/status');
        const data = await response.json();
        return data.logged_in === true;
    } catch (error) {
        console.error('Ошибка проверки авторизации:', error);
        return false;
    }
}

// === Оформление заказа и оплата через СБП ===

function showPaymentModal(orderId, amount) {
    const modal = document.getElementById('payment-modal');
    if (!modal) return;

    document.getElementById('sbp-amount').textContent = `${amount.toFixed(2)} RUB`;
    document.getElementById('sbp-order-id').textContent = orderId;

    const qrContainer = document.getElementById('qr-container');
    if (qrContainer) {
        qrContainer.innerHTML = `
            <img src="/generate-qr/${orderId}?t=${Date.now()}"
                 alt="QR-код СБП"
                 class="qr-code"
                 onerror="handleQrError(this)">
        `;
    }

    modal.style.display = 'block';
}

function handleQrError(imgElement) {
    console.error('Ошибка загрузки QR-кода');
    const container = imgElement.parentNode;
    if (container) {
        container.innerHTML = '<p class="qr-error">Не удалось загрузить QR-код. Пожалуйста, обновите страницу.</p>';
    }
    imgElement.style.display = 'none';
}

function closePaymentModal() {
    const modal = document.getElementById('payment-modal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
}

async function checkout() {
    // Проверка авторизации
    const loggedIn = await isUserLoggedIn();
    if (!loggedIn) {
        alert('Для оформления заказа необходимо войти в аккаунт.');
        window.location.href = '/login';
        return;
    }

    const cart = await getCart();

    if (Object.keys(cart.btc).length === 0 && Object.keys(cart.btb).length === 0) {
        alert('Ваша корзина пуста!');
        return;
    }

    if (!confirm('Вы уверены, что хотите оформить заказ?')) return;

    try {
        const orderItems = [];
        let total = 0;

        for (const [category, products] of Object.entries(cart)) {
            for (const [productId, item] of Object.entries(products)) {
                orderItems.push({
                    product_id: productId,
                    name: item.product_info.name,
                    quantity: item.quantity,
                    price: item.product_info.price,
                    sum: item.product_info.price * item.quantity,
                    category: category
                });
                total += item.product_info.price * item.quantity;
            }
        }

        if (total <= 0) throw new Error('Сумма заказа должна быть больше 0');

        const orderData = {
            items: orderItems,
            total: total,
            timestamp: new Date().toISOString(),
            status: 'pending'
        };

        const orderResponse = await fetch('/api/orders/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(orderData)
        });

        if (!orderResponse.ok) {
            const errorData = await orderResponse.json();
            throw new Error(errorData.message || 'Ошибка при оформлении заказа');
        }

        const orderResult = await orderResponse.json();

        if (orderResult.status !== 'success') {
            throw new Error('Не удалось создать заказ');
        }

        showPaymentModal(orderResult.order_id, orderResult.amount);
        await fetch('/api/cart/clear', { method: 'POST' });

        const cartItemsContainer = document.getElementById('cart-items');
        if (cartItemsContainer) {
            const items = cartItemsContainer.querySelectorAll('.cart-item');
            items.forEach(item => item.remove());
            const totalBlock = cartItemsContainer.querySelector('.cart-total');
            if (totalBlock) totalBlock.remove();
            if (!cartItemsContainer.querySelector('p')) {
                const emptyMessage = document.createElement('p');
                emptyMessage.textContent = 'Ваша корзина пуста';
                cartItemsContainer.appendChild(emptyMessage);
            }
        }

        const cartCounter = document.getElementById('cart-count');
        if (cartCounter) cartCounter.textContent = '0';

    } catch (error) {
        console.error('Ошибка оформления заказа:', error);
        alert(`Ошибка: ${error.message}`);
    }
}

// === Инициализация при загрузке страницы ===

document.addEventListener('DOMContentLoaded', () => {
    const checkoutBtn = document.querySelector('.btn-checkout');
    if (checkoutBtn) {
        checkoutBtn.addEventListener('click', checkout);
    }

    const modal = document.getElementById('payment-modal');
    if (modal) {
        const closeBtn = modal.querySelector('.close');
        if (closeBtn) {
            closeBtn.addEventListener('click', closePaymentModal);
        }
        window.addEventListener('click', (e) => {
            if (e.target === modal) closePaymentModal();
        });
    }
});