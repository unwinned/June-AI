import { ECPairFactory } from 'ecpair';
import * as bitcoin from 'bitcoinjs-lib';
import { BIP32Factory } from 'bip32';
import * as bip39 from 'bip39';
import * as ecc from 'tiny-secp256k1';
import { createHash } from 'crypto';
import {Signer} from "./bip322-js/dist/index.js";


bitcoin.initEccLib(ecc);
const ECPair = ECPairFactory(ecc);
const bip32 = BIP32Factory(ecc);

// ✅ 1. Генеруємо Taproot (P2TR) ключі у Testnet
const mnemonic = "spoon veteran game jungle abandon advice couch soap earth winner match mansion";
const seed2 = bip39.mnemonicToSeedSync(mnemonic);
const hdKey = bip32.fromSeed(seed2, bitcoin.networks.testnet);

// ✅ Використовуємо Taproot (P2TR) шлях: `m/86'/1'/0'/0/0`
const path3 = "m/86'/0'/0'/0/0";  // '1' означає Testnet
const child2 = hdKey.derivePath(path3);

// ✅ Отримуємо Taproot-адресу
const { address } = bitcoin.payments.p2tr({
  internalPubkey: Buffer.from(child2.publicKey.slice(1, 33)), // ⬅ Конвертація у Buffer
  network: bitcoin.networks.testnet,
});
console.log(Buffer.from(child2.publicKey.slice(1, 33)).toString('hex'))
const wif3 = child2.toWIF();
console.log("🔹 Taproot Address (Testnet):", address);
console.log("🔹 Private Key (WIF):", wif3);

// ✅ 2. Створюємо хеш повідомлення (SHA-256)
const message = "Please sign this message to prove ownership of your wallet. Unique code: 6484509866465351";
const messageHash = createHash('sha256').update(message).digest();

// ✅ 3. Підписуємо повідомлення через Schnorr (BIP-340)
const signature = ecc.signSchnorr(messageHash, child2.privateKey);

console.log("🔹 Message Signature (HEX):", Buffer.from(signature).toString("hex"));
console.log("🔹 Message Signature (Base64):", Buffer.from(signature).toString("base64"));

function sign_message_bip322(wif, address, message){
    return Signer.sign(wif, address, message);
}
const sig = sign_message_bip322(wif3, address, messageHash);
console.log(sig)